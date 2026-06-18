"""The append-only provenance ledger.

This ties the pieces together: every transition is appended as an `Entry`, linked
to the previous one by hash, and persisted durably in SQLite. The ledger can:

  - append(...)        record a new transition
  - get / head / iter  read history back
  - verify(...)        prove the whole chain (or a prefix) is intact
  - merkle_root(...)   produce a single commitment over the log (or a prefix)

It is deliberately *append-only*: there is no public update or delete. History in
an audit trail must be immutable, so the only legal mutation is "add the next
entry." (Rollback, later, is done by *replaying a prefix onto a fresh store* —
never by erasing the past.)

Why SQLite? It's in the Python standard library (no install), it's a real ACID
database with genuine crash-safety, and its WAL journal mode is itself a textbook
write-ahead log — the exact durability primitive this project is about.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Iterator, Optional

from .entry import GENESIS_PARENT_HASH, Entry
from .merkle import merkle_root as _merkle_root


class LedgerError(Exception):
    """Base class for ledger problems."""


class TamperError(LedgerError):
    """Raised when verification finds the chain has been altered."""


class Ledger:
    def __init__(self, path: str | Path = ":memory:") -> None:
        """Open (or create) a ledger.

        `:memory:` gives a throwaway in-RAM database — perfect for tests. A file
        path gives a durable on-disk ledger.
        """
        self._path = str(path)
        # check_same_thread=False keeps things simple for now; concurrency and
        # the consensus layer will revisit threading later.
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row  # rows accessible by column name

        if self._path != ":memory:":
            # WAL = write-ahead logging: changes are first appended to a -wal
            # sidecar file, then later checkpointed into the main db. It survives
            # crashes and lets readers proceed while a write is in flight.
            self._conn.execute("PRAGMA journal_mode=WAL")
        # FULL = fsync on every commit. Slower, but a committed entry is truly on
        # disk before append() returns — non-negotiable for an audit ledger.
        self._conn.execute("PRAGMA synchronous=FULL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                seq         INTEGER PRIMARY KEY,  -- also enforces uniqueness/order
                timestamp   REAL    NOT NULL,
                actor       TEXT    NOT NULL,
                action      TEXT    NOT NULL,
                payload     TEXT    NOT NULL,     -- canonical JSON
                parent_hash TEXT    NOT NULL,
                hash        TEXT    NOT NULL
            )
            """
        )
        self._conn.commit()

    # ----- writing -------------------------------------------------------------

    def append(
        self,
        actor: str,
        action: str,
        payload: dict,
        timestamp: Optional[float] = None,
    ) -> Entry:
        """Record one new transition and return the resulting Entry.

        The new entry's `seq` is head+1 and its `parent_hash` is the current
        head's hash, so the chain extends by exactly one link. The whole thing is
        a single committed transaction: either the row lands durably or it
        doesn't land at all (atomicity).
        """
        if timestamp is None:
            timestamp = time.time()

        head = self.head()
        seq = 0 if head is None else head.seq + 1
        parent_hash = GENESIS_PARENT_HASH if head is None else head.hash

        entry = Entry.create(seq, timestamp, actor, action, payload, parent_hash)

        # Store payload in the SAME canonical form used for hashing, so a
        # round-trip through the DB re-hashes identically.
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self._conn.execute(
            "INSERT INTO entries "
            "(seq, timestamp, actor, action, payload, parent_hash, hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                entry.seq,
                entry.timestamp,
                entry.actor,
                entry.action,
                payload_json,
                entry.parent_hash,
                entry.hash,
            ),
        )
        self._conn.commit()
        return entry

    # ----- reading -------------------------------------------------------------

    def _row_to_entry(self, row: sqlite3.Row) -> Entry:
        return Entry(
            seq=row["seq"],
            timestamp=row["timestamp"],
            actor=row["actor"],
            action=row["action"],
            payload=json.loads(row["payload"]),
            parent_hash=row["parent_hash"],
            hash=row["hash"],
        )

    def head(self) -> Optional[Entry]:
        """The most recent entry, or None if the ledger is empty."""
        row = self._conn.execute(
            "SELECT * FROM entries ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def get(self, seq: int) -> Entry:
        """The entry at position `seq` (raises LedgerError if absent)."""
        row = self._conn.execute(
            "SELECT * FROM entries WHERE seq = ?", (seq,)
        ).fetchone()
        if row is None:
            raise LedgerError(f"no entry at seq={seq}")
        return self._row_to_entry(row)

    def __len__(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]

    def __iter__(self) -> Iterator[Entry]:
        """Iterate entries in chain order (seq ascending)."""
        for row in self._conn.execute("SELECT * FROM entries ORDER BY seq ASC"):
            yield self._row_to_entry(row)

    # ----- integrity -----------------------------------------------------------

    def verify(self, up_to: Optional[int] = None) -> bool:
        """Walk the chain and prove it is internally consistent.

        Three independent checks per entry:
          1. seq is the next expected integer  -> no gaps / reordering
          2. parent_hash matches the previous entry's hash -> links intact
          3. the entry's stored hash matches a fresh recompute -> content intact

        Any failure means the history was altered, so we raise TamperError.
        Passing all three for every entry is a cryptographic proof of the exact
        sequence of transitions — the core guarantee Mnemosyne promises.

        `up_to` (inclusive seq) verifies only a prefix.
        """
        expected_seq = 0
        expected_parent = GENESIS_PARENT_HASH

        for entry in self:
            if up_to is not None and entry.seq > up_to:
                break

            if entry.seq != expected_seq:
                raise TamperError(
                    f"sequence gap: expected {expected_seq}, found {entry.seq}"
                )
            if entry.parent_hash != expected_parent:
                raise TamperError(
                    f"broken link at seq={entry.seq}: "
                    f"parent_hash {entry.parent_hash[:12]}... "
                    f"!= previous hash {expected_parent[:12]}..."
                )
            if not entry.is_valid():
                raise TamperError(
                    f"content tampered at seq={entry.seq}: "
                    f"hash {entry.hash[:12]}... != recomputed "
                    f"{entry.recompute_hash()[:12]}..."
                )

            expected_parent = entry.hash
            expected_seq += 1

        return True

    def verify_prefix(self, length: int) -> bool:
        """Verify the first `length` entries (seq 0 .. length-1)."""
        if length <= 0:
            return True
        return self.verify(up_to=length - 1)

    def merkle_root(self, up_to: Optional[int] = None) -> str:
        """A single hash committing to the log (or a prefix of it).

        Two ledgers with the same root hold the byte-identical sequence of
        entries — so replicas in the consensus layer can agree by comparing one
        short string instead of streaming the whole history.
        """
        hashes = [e.hash for e in self if up_to is None or e.seq <= up_to]
        return _merkle_root(hashes)

    # ----- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
