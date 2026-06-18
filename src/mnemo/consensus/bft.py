"""Byzantine fault-tolerant commit.

Plain Raft tolerates *crash* faults: a node either gives the right answer or no
answer (it's down). That assumption breaks for LLM agents — a hallucinating agent
returns a confident, well-formed, WRONG answer. That's a *Byzantine* fault, and
it needs a stronger quorum rule.

The classic BFT result: to tolerate up to `f` Byzantine nodes you need
`N = 3f + 1` replicas total, and you commit a value only when at least
`2f + 1` of them agree on it. With that margin, the honest replicas
(N - f = 2f + 1) always outnumber any coalition of liars, so a wrong value can
never reach quorum.

Here, "replicas" are independent re-derivations of the same transition (e.g. the
same prompt run N times, or N models). Each produces an output; we fingerprint
each output and tally the fingerprints. Only a value backed by >= 2f+1 identical
fingerprints gets appended to the ledger. A Byzantine replica's divergent output
simply fails to gather votes and is discarded.

This is the "can we trust this state transition enough to commit it?" gate that
sits in front of the provenance ledger.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from ..ledger import Entry, Ledger, fingerprint

# A replica is just another (inputs -> output) derivation of the transition.
Replica = Callable[[dict], Any]


@dataclass(frozen=True)
class Vote:
    replica_id: str
    digest: str  # fingerprint of that replica's output


class NoQuorumError(Exception):
    """Raised when no value reaches the 2f+1 agreement threshold.

    Refusing to commit is the safe outcome: better to escalate to a human than to
    write an untrusted transition into the ledger.
    """


@dataclass(frozen=True)
class CommitResult:
    entry: Entry            # the committed ledger entry
    output: Any             # the agreed-upon output
    votes: int              # how many replicas backed it
    total: int              # how many replicas responded


class BFTConsensus:
    def __init__(self, ledger: Ledger, replicas: List[Replica], f: int = 1) -> None:
        """`f` is the number of Byzantine faults to tolerate.

        We require N >= 3f + 1 replicas so a 2f+1 quorum is achievable even with
        f liars and f more unavailable.
        """
        required = 3 * f + 1
        if len(replicas) < required:
            raise ValueError(
                f"need at least {required} replicas to tolerate f={f} "
                f"Byzantine faults, got {len(replicas)}"
            )
        self.ledger = ledger
        self.replicas = replicas
        self.f = f

    @property
    def quorum(self) -> int:
        """Votes required to commit: 2f + 1."""
        return 2 * self.f + 1

    def propose(self, actor: str, action: str, inputs: dict) -> CommitResult:
        """Run the transition across all replicas; commit only on quorum.

        Steps:
          1. Each replica independently derives an output (a crash = no vote).
          2. Fingerprint each output and tally the fingerprints.
          3. If the top fingerprint has >= 2f+1 votes, append the agreed output
             to the ledger. Otherwise raise NoQuorumError (commit nothing).
        """
        votes: List[Vote] = []
        outputs_by_digest: Dict[str, Any] = {}

        for i, replica in enumerate(self.replicas):
            try:
                out = replica(inputs)
            except Exception:
                # A crashed/unavailable replica simply doesn't vote — exactly the
                # fault Raft already handles. BFT additionally handles the liars.
                continue
            digest = fingerprint(out)
            votes.append(Vote(f"replica-{i}", digest))
            outputs_by_digest.setdefault(digest, out)

        if not votes:
            raise NoQuorumError("no replica responded")

        tally = Counter(v.digest for v in votes)
        winning_digest, count = tally.most_common(1)[0]

        if count < self.quorum:
            raise NoQuorumError(
                f"no quorum: best value had {count}/{len(self.replicas)} votes, "
                f"need {self.quorum}"
            )

        agreed_output = outputs_by_digest[winning_digest]
        entry = self.ledger.append(
            actor,
            action,
            {
                "inputs": inputs,
                "output": agreed_output,
                "votes": count,
                "replicas": len(self.replicas),
            },
        )
        return CommitResult(entry, agreed_output, count, len(votes))
