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


# --- v2.0: normalization -------------------------------------------------------

def test_normalization_lets_equivalent_outputs_vote_together():
    # Four agents give the same answer in different spellings.
    reps = [
        lambda i: {"ans": "Paris"},
        lambda i: {"ans": "paris"},
        lambda i: {"ans": "PARIS"},
        lambda i: {"ans": "Paris"},
    ]

    # Without normalization: "Paris" appears twice, others once -> max 2 < quorum 3.
    with pytest.raises(NoQuorumError):
        BFTConsensus(Ledger(), reps, f=1).propose("a", "capital", {})

    # With a lowercasing normalizer, all four collapse to one value -> commits.
    norm = lambda o: {"ans": o["ans"].lower()}
    res = BFTConsensus(Ledger(), reps, f=1, normalize=norm).propose("a", "capital", {})
    assert res.votes == 4
    assert res.output["ans"].lower() == "paris"


# --- v2.0: verifier overrides the vote ----------------------------------------

# Oracle: the answer is correct iff val**2 == target (a checkable square root).
def sqrt_verifier(inputs, out):
    return out["val"] ** 2 == inputs["target"]


def test_verifier_rejects_confident_wrong_majority():
    # 3 agents confidently say 5 (wrong: 25 != 16); 1 says 4 (right).
    reps = [
        lambda i: {"val": 5},
        lambda i: {"val": 5},
        lambda i: {"val": 5},
        lambda i: {"val": 4},
    ]
    led = Ledger()
    # The wrong majority is filtered out; only the verified answer (1 vote)
    # survives, which is below the default quorum -> refuse to commit.
    with pytest.raises(NoQuorumError):
        BFTConsensus(led, reps, f=1, verifier=sqrt_verifier).propose(
            "a", "sqrt", {"target": 16}
        )
    assert len(led) == 0


def test_trusted_verifier_commits_lone_correct_answer():
    reps = [
        lambda i: {"val": 5},
        lambda i: {"val": 5},
        lambda i: {"val": 5},
        lambda i: {"val": 4},
    ]
    led = Ledger()
    # With a sound oracle we can lower the threshold: the single verified-correct
    # answer wins despite losing the vote 3-to-1.
    res = BFTConsensus(
        led, reps, f=1, verifier=sqrt_verifier, min_votes=1
    ).propose("a", "sqrt", {"target": 16})
    assert res.output == {"val": 4}
    assert res.rejected == 3
    assert len(led) == 1


def test_verifier_and_normalizer_together():
    # Correct answers in different spellings, plus one wrong answer that the
    # verifier must drop before voting.
    reps = [
        lambda i: {"val": 4, "note": "four"},
        lambda i: {"val": 4, "note": "FOUR"},
        lambda i: {"val": 4, "note": "Four"},
        lambda i: {"val": 9, "note": "nine"},  # wrong: 81 != 16
    ]
    norm = lambda o: {"val": o["val"]}  # ignore the noisy free-text note
    res = BFTConsensus(
        Ledger(), reps, f=1, verifier=sqrt_verifier, normalize=norm
    ).propose("a", "sqrt", {"target": 16})
    assert res.output["val"] == 4
    assert res.votes == 3
    assert res.rejected == 1
