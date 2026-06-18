"""Tests for the provenance ledger.

These aren't just "does it run" checks — the tamper tests are the *demonstration*
that the integrity guarantees hold: we deliberately corrupt the underlying store
and assert that verification catches it.
"""

import json

import pytest

from mnemo.ledger import Entry, Ledger, TamperError, merkle_root
from mnemo.ledger.entry import GENESIS_PARENT_HASH


def test_append_assigns_sequential_seqs():
    led = Ledger()
    e0 = led.append("agentA", "plan", {"step": 1})
    e1 = led.append("agentB", "act", {"step": 2})
    assert e0.seq == 0
    assert e1.seq == 1
    assert len(led) == 2


def test_genesis_links_to_sentinel():
    led = Ledger()
    e0 = led.append("system", "init", {})
    assert e0.parent_hash == GENESIS_PARENT_HASH


def test_each_entry_links_to_previous():
    led = Ledger()
    e0 = led.append("a", "x", {})
    e1 = led.append("a", "y", {})
    assert e1.parent_hash == e0.hash


def test_roundtrip_preserves_entry_and_hash():
    led = Ledger()
    written = led.append("a", "x", {"k": "v", "n": 3})
    read = led.get(0)
    assert read == written          # frozen dataclass equality, field-by-field
    assert read.is_valid()          # hash still matches content after DB round-trip


def test_verify_passes_on_clean_chain():
    led = Ledger()
    for i in range(5):
        led.append("a", "step", {"i": i})
    assert led.verify() is True


def test_verify_detects_content_tampering():
    led = Ledger()
    led.append("a", "transfer", {"amount": 10})
    led.append("a", "transfer", {"amount": 20})

    # Reach under the API and rewrite a payload, leaving its hash untouched.
    led._conn.execute(
        "UPDATE entries SET payload = ? WHERE seq = 0",
        (json.dumps({"amount": 9999}, sort_keys=True, separators=(",", ":")),),
    )
    led._conn.commit()

    with pytest.raises(TamperError):
        led.verify()


def test_verify_detects_broken_link():
    led = Ledger()
    led.append("a", "x", {})
    led.append("a", "y", {})

    # Corrupt the parent pointer of the second entry.
    led._conn.execute(
        "UPDATE entries SET parent_hash = ? WHERE seq = 1", ("f" * 64,)
    )
    led._conn.commit()

    with pytest.raises(TamperError):
        led.verify()


def test_verify_detects_deleted_entry():
    led = Ledger()
    for i in range(3):
        led.append("a", "step", {"i": i})

    # Remove a middle entry -> a sequence gap appears.
    led._conn.execute("DELETE FROM entries WHERE seq = 1")
    led._conn.commit()

    with pytest.raises(TamperError):
        led.verify()


def test_verify_prefix_only_checks_prefix():
    led = Ledger()
    led.append("a", "x", {})        # seq 0 (clean)
    led.append("a", "y", {})        # seq 1 (about to be corrupted)

    led._conn.execute("UPDATE entries SET actor = 'evil' WHERE seq = 1")
    led._conn.commit()

    # The clean prefix [0] still verifies...
    assert led.verify_prefix(1) is True
    # ...but the full chain does not.
    with pytest.raises(TamperError):
        led.verify()


def test_merkle_root_changes_with_history():
    led = Ledger()
    led.append("a", "x", {})
    r1 = led.merkle_root()
    led.append("a", "y", {})
    r2 = led.merkle_root()
    assert r1 != r2


def test_merkle_root_is_deterministic_across_ledgers():
    led1 = Ledger()
    led2 = Ledger()
    # Same content + same timestamps -> identical entries -> identical roots.
    for i in range(4):
        led1.append("a", "step", {"i": i}, timestamp=100 + i)
        led2.append("a", "step", {"i": i}, timestamp=100 + i)
    assert led1.merkle_root() == led2.merkle_root()


def test_merkle_root_empty_is_stable():
    led = Ledger()
    assert led.merkle_root() == merkle_root([])


def test_persists_to_disk(tmp_path):
    db = tmp_path / "ledger.db"
    led = Ledger(db)
    led.append("a", "x", {"v": 1})
    led.close()

    reopened = Ledger(db)
    assert len(reopened) == 1
    assert reopened.verify() is True
    assert reopened.get(0).payload == {"v": 1}
    reopened.close()
