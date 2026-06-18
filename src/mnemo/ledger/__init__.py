"""Cryptographic provenance ledger.

A hash-chained, Merkle-rooted, append-only write-ahead log of every state
transition, so any prefix of history can be cryptographically verified and
tampering is detectable.

Public API:
    Ledger              the append-only store
    Entry               one immutable record in the chain
    LedgerError         base error
    TamperError         raised when verification detects alteration
    merkle_root         fold a list of leaf hashes into one root
"""

from .entry import (
    GENESIS_PARENT_HASH,
    Entry,
    canonical_bytes,
    compute_hash,
    fingerprint,
)
from .ledger import Ledger, LedgerError, TamperError
from .merkle import merkle_root

__all__ = [
    "Ledger",
    "Entry",
    "LedgerError",
    "TamperError",
    "merkle_root",
    "compute_hash",
    "fingerprint",
    "canonical_bytes",
    "GENESIS_PARENT_HASH",
]
