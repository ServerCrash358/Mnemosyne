"""A single, immutable record in the provenance ledger.

Every state transition in a Mnemosyne swarm becomes one `Entry`. Entries are
linked into a *hash chain*: each entry stores the hash of the one before it, and
its own hash is computed over its contents *including* that parent hash. Change
any byte of any earlier entry and every hash after it stops matching — which is
exactly the tamper-evidence we want for an audit trail.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

# The very first entry has no predecessor, so it points at a fixed sentinel.
# 64 zeros = the hex width of a SHA-256 digest, so it "looks like" a hash.
GENESIS_PARENT_HASH = "0" * 64


def canonical_bytes(obj: Any) -> bytes:
    """Serialize `obj` to a single, canonical byte string.

    Hashing is only meaningful if the *same logical value* always produces the
    *same bytes*. Plain `json.dumps` doesn't guarantee that — `{"a":1,"b":2}` and
    `{"b":2,"a":1}` are equal dicts but serialize differently by default. So we
    pin down every degree of freedom:

      - sort_keys=True     -> key order is fixed
      - separators no space-> no incidental whitespace differences
      - ensure_ascii=False -> a character is encoded one way (then utf-8 below)

    This "canonicalization" step is what makes a hash reproducible across runs,
    machines, and Python versions.
    """
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def fingerprint(obj: Any) -> str:
    """A stable SHA-256 fingerprint of any JSON-serializable value.

    Used wherever we need to ask "are these two values the same?" by comparing
    one short string instead of the whole structure — e.g. replay divergence
    checks and consensus vote tallies.
    """
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


def compute_hash(
    seq: int,
    timestamp: float,
    actor: str,
    action: str,
    payload: dict,
    parent_hash: str,
) -> str:
    """Return the SHA-256 hex digest that uniquely fingerprints this entry.

    The digest covers *all* of the entry's content fields plus the parent hash.
    Including `parent_hash` is what chains entries together: the fingerprint of
    entry N depends on entry N-1, whose fingerprint depends on N-2, and so on
    back to genesis.
    """
    preimage = {
        "seq": seq,
        "timestamp": timestamp,
        "actor": actor,
        "action": action,
        "payload": payload,
        "parent_hash": parent_hash,
    }
    return hashlib.sha256(canonical_bytes(preimage)).hexdigest()


@dataclass(frozen=True)
class Entry:
    """One immutable transition in the ledger.

    `frozen=True` makes instances read-only: once created, an Entry can't be
    mutated. That matches the domain — a committed historical fact should never
    change in place — and lets us treat its hash as a stable identity.
    """

    seq: int            # monotonic position in the chain, starting at 0
    timestamp: float    # wall-clock time the transition was recorded (unix secs)
    actor: str          # who caused it (agent id, "system", etc.)
    action: str         # short label for the kind of transition
    payload: dict       # the transition's data (must be JSON-serializable)
    parent_hash: str    # hash of the previous entry (GENESIS_PARENT_HASH if first)
    hash: str           # this entry's own fingerprint

    @classmethod
    def create(
        cls,
        seq: int,
        timestamp: float,
        actor: str,
        action: str,
        payload: dict,
        parent_hash: str,
    ) -> "Entry":
        """Build an Entry, computing its hash from the content fields."""
        h = compute_hash(seq, timestamp, actor, action, payload, parent_hash)
        return cls(seq, timestamp, actor, action, payload, parent_hash, h)

    def recompute_hash(self) -> str:
        """Recompute the hash from the content fields, ignoring the stored one."""
        return compute_hash(
            self.seq,
            self.timestamp,
            self.actor,
            self.action,
            self.payload,
            self.parent_hash,
        )

    def is_valid(self) -> bool:
        """True iff the stored hash still matches the content (no tampering)."""
        return self.hash == self.recompute_hash()
