"""Tests for rollback: state reconstruction and saga compensation."""

from mnemo.ledger import Ledger
from mnemo.rollback import SagaRegistry, rebuild_state, state_at


# A tiny key-value reducer: each entry's payload carries {"set": {...}} ops.
def kv_reducer(state, entry):
    new = dict(state)
    for k, v in entry.payload.get("set", {}).items():
        new[k] = v
    for k in entry.payload.get("del", []):
        new.pop(k, None)
    return new


def _seed():
    led = Ledger()
    led.append("a", "op", {"set": {"x": 1}})            # seq 0
    led.append("a", "op", {"set": {"y": 2}})            # seq 1
    led.append("a", "op", {"set": {"x": 99}})           # seq 2
    led.append("a", "op", {"del": ["y"]})               # seq 3
    return led


def test_rebuild_full_state():
    led = _seed()
    assert rebuild_state(led, kv_reducer) == {"x": 99}


def test_rollback_to_prefix():
    led = _seed()
    # State right after seq 1, before x was overwritten and y deleted.
    assert state_at(led, kv_reducer, seq=1) == {"x": 1, "y": 2}


def test_rebuild_does_not_mutate_initial_state():
    led = _seed()
    base = {"x": 0}
    rebuild_state(led, kv_reducer, initial_state=base)
    assert base == {"x": 0}  # untouched


def test_saga_compensates_in_reverse():
    led = Ledger()
    led.append("infra", "drain_traffic", {"svc": "X"})   # seq 0
    led.append("infra", "scale_up", {"svc": "X", "by": 3})  # seq 1
    led.append("infra", "restart", {"svc": "X"})         # seq 2

    undone_order = []
    saga = SagaRegistry()

    @saga.compensator("scale_up")
    def undo_scale(entry):
        undone_order.append(("scale_down", entry.payload["by"]))

    @saga.compensator("drain_traffic")
    def undo_drain(entry):
        undone_order.append(("restore_traffic", entry.payload["svc"]))

    # restart has no compensator -> skipped (no external effect to undo)
    undone = saga.compensate_to(led, target_seq=-1)  # undo everything

    assert undone_order == [
        ("scale_down", 3),         # seq 1 undone before...
        ("restore_traffic", "X"),  # ...seq 0  (reverse order)
    ]
    assert [e.seq for e in undone] == [1, 0]


def test_saga_only_undoes_after_target():
    led = Ledger()
    led.append("infra", "scale_up", {"by": 1})   # seq 0 (keep)
    led.append("infra", "scale_up", {"by": 2})   # seq 1 (undo)

    seen = []
    saga = SagaRegistry()

    @saga.compensator("scale_up")
    def undo(entry):
        seen.append(entry.payload["by"])

    saga.compensate_to(led, target_seq=0)  # keep seq 0, undo seq 1 only
    assert seen == [2]
