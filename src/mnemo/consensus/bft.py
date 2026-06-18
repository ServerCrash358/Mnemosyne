"""Byzantine fault-tolerant commit — verifier-first edition (v2.0).

Plain Raft tolerates *crash* faults: a node either gives the right answer or no
answer. That breaks for LLM agents — a hallucinating agent returns a confident,
well-formed, WRONG answer. That's a *Byzantine* fault, and it needs a stronger
quorum rule:

    To tolerate up to `f` Byzantine nodes you need N = 3f + 1 replicas, and you
    commit a value only when at least 2f + 1 of them agree on it.

But raw voting has two real-world holes that v2.0 closes:

  1. COMPARISON IS TOO LITERAL. Two correct answers can be spelled differently
     ("x**2/2 + C" vs "0.5*x**2 + C") and so never vote together. Fix: a
     pluggable `normalize` that collapses equivalent outputs to one canonical
     form *before* fingerprinting. (Same idea as canonical JSON in the ledger.)

  2. THE MAJORITY CAN BE WRONG. Agents that share a model fail in correlated
     ways, so 5/5 agreement proves nothing. Voting yields *agreement*, not
     *truth*. Fix: an optional `verifier(inputs, output) -> bool` that filters to
     provably-correct outputs BEFORE voting. Where a sound oracle exists (e.g.
     differentiate an integral and check it equals the integrand), the verifier
     is your real source of truth and voting is demoted to a tiebreaker.

Pipeline per proposal:   derive -> verify (filter) -> normalize -> vote -> commit
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ..ledger import Entry, Ledger, fingerprint

# A replica is an independent (inputs -> output) derivation of the transition.
Replica = Callable[[dict], Any]
# Maps an output to a canonical form used only for vote comparison.
Normalizer = Callable[[Any], Any]
# Returns True iff an output is provably correct for the given inputs.
Verifier = Callable[[dict, Any], bool]


@dataclass(frozen=True)
class Vote:
    replica_id: str
    digest: str  # fingerprint of that replica's *normalized* output


class NoQuorumError(Exception):
    """Raised when no value reaches the agreement threshold.

    Refusing to commit is the safe outcome: escalate to a human rather than write
    an untrusted transition into the ledger.
    """


@dataclass(frozen=True)
class CommitResult:
    entry: Entry        # the committed ledger entry
    output: Any         # the agreed-upon (raw) output
    votes: int          # how many replicas backed the winning value
    total: int          # how many replicas produced a usable (verified) output
    rejected: int = 0   # how many outputs the verifier threw out


class BFTConsensus:
    def __init__(
        self,
        ledger: Ledger,
        replicas: List[Replica],
        f: int = 1,
        *,
        normalize: Optional[Normalizer] = None,
        verifier: Optional[Verifier] = None,
        min_votes: Optional[int] = None,
    ) -> None:
        """
        f          number of Byzantine faults to tolerate (needs N >= 3f+1).
        normalize  optional canonicalizer applied before comparing outputs.
                   Default: identity (compare raw outputs).
        verifier   optional oracle; outputs that fail it are discarded before
                   voting. Default: None (no verification — pure voting).
        min_votes  override the agreement threshold. Defaults to the BFT quorum
                   2f+1. Lower it (e.g. to 1) ONLY when `verifier` is a sound
                   oracle, since a verified output is correct on its own.
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
        self.normalize: Normalizer = normalize or (lambda x: x)
        self.verifier = verifier
        self._min_votes = min_votes

    @property
    def quorum(self) -> int:
        """Votes required to commit (2f+1 unless overridden by min_votes)."""
        return self._min_votes if self._min_votes is not None else 2 * self.f + 1

    def _verify(self, inputs: dict, output: Any) -> bool:
        """Run the verifier defensively: a throwing verifier == not verified."""
        if self.verifier is None:
            return True
        try:
            return bool(self.verifier(inputs, output))
        except Exception:
            return False

    def propose(self, actor: str, action: str, inputs: dict) -> CommitResult:
        """Run the transition across replicas; commit only on quorum.

        derive -> verify (filter) -> normalize -> tally -> commit-or-refuse.
        """
        votes: List[Vote] = []
        outputs_by_digest: Dict[str, Any] = {}
        rejected = 0

        for i, replica in enumerate(self.replicas):
            try:
                out = replica(inputs)
            except Exception:
                # Crashed/unavailable replica simply doesn't vote (Raft's case).
                continue

            if not self._verify(inputs, out):
                # Provably-wrong output is discarded REGARDLESS of how many
                # peers agree with it — the verifier outranks the vote.
                rejected += 1
                continue

            digest = fingerprint(self.normalize(out))
            votes.append(Vote(f"replica-{i}", digest))
            outputs_by_digest.setdefault(digest, out)

        if not votes:
            why = (
                "no replica produced a verified, valid output"
                if self.verifier is not None
                else "no replica responded"
            )
            raise NoQuorumError(why)

        tally = Counter(v.digest for v in votes)
        winning_digest, count = tally.most_common(1)[0]

        if count < self.quorum:
            raise NoQuorumError(
                f"no quorum: best value had {count} vote(s) "
                f"({rejected} rejected by verifier), need {self.quorum}"
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
                "rejected": rejected,
            },
        )
        return CommitResult(entry, agreed_output, count, len(votes), rejected)
