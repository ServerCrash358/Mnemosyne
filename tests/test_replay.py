"""Tests for the record/replay engine.

The headline test is `test_replay_does_not_call_fn`: it proves a replayed run
reproduces outputs WITHOUT invoking the (stochastic) agent body — the core claim.
"""

import itertools

import pytest

from mnemo.ledger import Ledger
from mnemo.replay import RECORD, REPLAY, DivergenceError, ReplayEngine


def test_record_returns_live_output_and_logs_it():
    led = Ledger()
    eng = ReplayEngine(led, mode=RECORD)
    out = eng.step("a", "invoke", {"x": 1}, lambda i: {"y": i["x"] + 1})
    assert out == {"y": 2}
    assert led.get(0).payload["output"] == {"y": 2}


def test_replay_reproduces_recorded_output():
    led = Ledger()
    rec = ReplayEngine(led, mode=RECORD)
    rec.step("a", "invoke", {"x": 1}, lambda i: {"y": i["x"] + 1})

    rep = ReplayEngine(led, mode=REPLAY)
    out = rep.step("a", "invoke", {"x": 1}, lambda i: {"y": 999})  # fn should be ignored
    assert out == {"y": 2}


def test_replay_does_not_call_fn():
    led = Ledger()
    # A non-deterministic source: returns a different value every call.
    counter = itertools.count()
    nondet = lambda i: {"v": next(counter)}

    rec = ReplayEngine(led, mode=RECORD)
    recorded = rec.step("a", "invoke", {}, nondet)  # records v=0

    calls = []
    def tripwire(i):
        calls.append(1)
        return {"v": next(counter)}

    rep = ReplayEngine(led, mode=REPLAY)
    replayed = rep.step("a", "invoke", {}, tripwire)

    assert replayed == recorded   # same output as the original run
    assert calls == []            # the function was never invoked


def test_replay_detects_divergence():
    led = Ledger()
    rec = ReplayEngine(led, mode=RECORD)
    rec.step("a", "invoke", {"x": 1}, lambda i: {"ok": True})

    rep = ReplayEngine(led, mode=REPLAY)
    with pytest.raises(DivergenceError):
        rep.step("a", "invoke", {"x": 2}, lambda i: {"ok": True})  # different input


def test_replay_past_end_raises():
    led = Ledger()
    ReplayEngine(led, mode=RECORD).step("a", "invoke", {}, lambda i: {})
    rep = ReplayEngine(led, mode=REPLAY)
    rep.step("a", "invoke", {}, lambda i: {})        # consumes the only entry
    with pytest.raises(DivergenceError):
        rep.step("a", "invoke", {}, lambda i: {})    # nothing left to replay
