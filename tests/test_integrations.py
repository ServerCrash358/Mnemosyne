"""Tests for the framework adapter (MnemoRuntime).

Framework-agnostic: we simulate a graph as a plain list of nodes run in order, so
these tests don't depend on LangGraph being installed. The adapter wraps
`state -> update` callables, which is exactly LangGraph/AutoGen's node contract.
"""

import itertools

import pytest

from mnemo.integrations import MnemoRuntime
from mnemo.ledger import Ledger
from mnemo.replay import RECORD, REPLAY, DivergenceError


def run_pipeline(nodes, state):
    """Minimal stand-in for a graph runner: thread state through nodes in order."""
    for node in nodes:
        update = node(state)
        state = {**state, **update}
    return state


def test_governed_record_writes_to_ledger():
    led = Ledger()
    rt = MnemoRuntime(led, mode=RECORD)
    nodes = [
        rt.govern("A", lambda s: {"n": s["n"] + 1}),
        rt.govern("B", lambda s: {"n": s["n"] * 10}),
    ]
    out = run_pipeline(nodes, {"n": 0})
    assert out["n"] == 10
    assert [e.actor for e in led] == ["A", "B"]


def test_governed_replay_reproduces_without_calling_fn():
    # Non-deterministic nodes: a fresh live run would differ; replay must not.
    counter = itertools.count()

    def make(name):
        return lambda s: {"trace": s.get("trace", []) + [next(counter)]}

    led = Ledger()
    rt_rec = MnemoRuntime(led, RECORD)
    rec_nodes = [rt_rec.govern("A", make("A")), rt_rec.govern("B", make("B"))]
    recorded = run_pipeline(rec_nodes, {})

    calls = []
    def tripwire_A(s):
        calls.append("A")
        return {"trace": s.get("trace", []) + [next(counter)]}
    def tripwire_B(s):
        calls.append("B")
        return {"trace": s.get("trace", []) + [next(counter)]}

    rt_rep = MnemoRuntime(led, REPLAY)
    rep_nodes = [rt_rep.govern("A", tripwire_A), rt_rep.govern("B", tripwire_B)]
    replayed = run_pipeline(rep_nodes, {})

    assert replayed == recorded
    assert calls == []  # node bodies never invoked during replay


def test_governed_replay_detects_divergence():
    led = Ledger()
    rt = MnemoRuntime(led, RECORD)
    run_pipeline([rt.govern("A", lambda s: {"ok": True})], {"x": 1})

    rt_rep = MnemoRuntime(led, REPLAY)
    with pytest.raises(DivergenceError):
        run_pipeline([rt_rep.govern("A", lambda s: {"ok": True})], {"x": 2})


def test_consensus_governed_node_outvotes_byzantine():
    led = Ledger()
    rt = MnemoRuntime(led, RECORD)
    honest = lambda s: {"decision": "restart"}
    liar = lambda s: {"decision": "delete_everything"}
    node = rt.govern("decide", replicas=[honest, honest, honest, liar], f=1)
    out = node({"svc": "X"})
    assert out["decision"] == "restart"
    assert led.verify() is True  # committed through the provenance chain


def test_consensus_governed_with_verifier():
    led = Ledger()
    rt = MnemoRuntime(led, RECORD)
    # sqrt oracle: correct iff val**2 == target
    verifier = lambda inp, out: out["val"] ** 2 == inp["target"]
    reps = [
        lambda s: {"val": 5},  # wrong (25)
        lambda s: {"val": 5},
        lambda s: {"val": 5},
        lambda s: {"val": 4},  # right (16)
    ]
    node = rt.govern("sqrt", replicas=reps, f=1, verifier=verifier, min_votes=1)
    out = node({"target": 16})
    assert out["val"] == 4  # verifier overrides the confident wrong majority


def test_int_replicas_shortcut():
    led = Ledger()
    rt = MnemoRuntime(led, RECORD)
    # replicas=4 -> run the same fn 4 times (correlated, but valid wiring)
    node = rt.govern("decide", lambda s: {"d": 1}, replicas=4, f=1)
    out = node({})
    assert out == {"d": 1}
