"""Tests for the swarm pipeline.

`test_swarm_replays_deterministically` is the money test: it shows a swarm built
from non-deterministic agents nonetheless reproduces a byte-identical run on
replay, because the engine serves recorded outputs.
"""

import itertools

from mnemo.agents import Agent, Swarm
from mnemo.ledger import Ledger
from mnemo.replay import RECORD, REPLAY, ReplayEngine


def test_swarm_threads_output_into_next_input():
    led = Ledger()
    eng = ReplayEngine(led, mode=RECORD)
    swarm = Swarm(
        [
            Agent("A", lambda i: {"n": i["n"] + 1}),
            Agent("B", lambda i: {"n": i["n"] * 10}),
            Agent("C", lambda i: {"n": i["n"] - 3}),
        ],
        eng,
    )
    result = swarm.run({"n": 0})
    # (0+1)=1 -> *10=10 -> -3=7
    assert result == {"n": 7}
    assert len(led) == 3
    assert [e.actor for e in led] == ["A", "B", "C"]


def test_swarm_replays_deterministically():
    # Each agent injects a fresh non-deterministic token, so a second *live* run
    # would differ. Replay must still reproduce the first run exactly.
    tokens = itertools.count()

    def make_agent(name):
        return Agent(name, lambda i: {"chain": i.get("chain", []) + [next(tokens)]})

    agents = [make_agent("A"), make_agent("B"), make_agent("C")]

    rec_led = Ledger()
    rec_run = Swarm(agents, ReplayEngine(rec_led, RECORD)).run({})

    # Replay over the same ledger; agent bodies would produce new tokens if called.
    rep_run = Swarm(agents, ReplayEngine(rec_led, REPLAY)).run({})

    assert rep_run == rec_run
