"""Tests for BFT consensus.

The key scenarios: honest replicas reach quorum and commit; a single Byzantine
liar is outvoted; too many liars => no quorum => nothing is committed.
"""

import pytest

from mnemo.consensus import BFTConsensus, NoQuorumError
from mnemo.ledger import Ledger


def honest(inputs):
    return {"action": "restart", "target": inputs["svc"]}


def liar(inputs):
    return {"action": "delete_everything", "target": inputs["svc"]}


def test_requires_enough_replicas():
    led = Ledger()
    with pytest.raises(ValueError):
        BFTConsensus(led, [honest, honest, honest], f=1)  # need 3f+1 = 4


def test_all_honest_commits():
    led = Ledger()
    bft = BFTConsensus(led, [honest] * 4, f=1)
    result = bft.propose("infra", "remediate", {"svc": "X"})
    assert result.output == {"action": "restart", "target": "X"}
    assert result.votes == 4
    assert len(led) == 1


def test_single_byzantine_is_outvoted():
    led = Ledger()
    # 3 honest + 1 liar, f=1. Honest value gets 3 >= 2f+1=3 votes -> commits.
    bft = BFTConsensus(led, [honest, honest, honest, liar], f=1)
    result = bft.propose("infra", "remediate", {"svc": "X"})
    assert result.output["action"] == "restart"   # the liar's value lost
    assert result.votes == 3


def test_too_many_byzantine_blocks_commit():
    led = Ledger()
    # 2 honest + 2 liars: best value only has 2 < quorum 3 -> no commit.
    bft = BFTConsensus(led, [honest, honest, liar, liar], f=1)
    with pytest.raises(NoQuorumError):
        bft.propose("infra", "remediate", {"svc": "X"})
    assert len(led) == 0  # nothing untrusted was written


def test_crashed_replica_does_not_block_quorum():
    def crasher(inputs):
        raise RuntimeError("node down")

    led = Ledger()
    # 3 honest + 1 crashed. Crash = no vote; 3 honest still reach quorum.
    bft = BFTConsensus(led, [honest, honest, honest, crasher], f=1)
    result = bft.propose("infra", "remediate", {"svc": "X"})
    assert result.votes == 3
    assert len(led) == 1


def test_committed_entry_is_in_verifiable_ledger():
    led = Ledger()
    bft = BFTConsensus(led, [honest] * 4, f=1)
    bft.propose("infra", "remediate", {"svc": "X"})
    assert led.verify() is True  # consensus output flows into the provenance chain
