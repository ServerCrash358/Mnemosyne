"""A tiny end-to-end tour of the ledger.

Run it:  python examples/demo_ledger.py
(from the project root, after `pip install -e .`)
"""

from mnemo.ledger import Ledger, TamperError


def main() -> None:
    led = Ledger()  # in-memory for the demo

    print("== appending a few agent transitions ==")
    led.append("planner", "make_plan", {"goal": "restart service X"})
    led.append("executor", "drain_traffic", {"service": "X"})
    led.append("executor", "restart", {"service": "X", "ok": True})

    for e in led:
        print(f"  seq={e.seq} {e.actor:9} {e.action:14} "
              f"hash={e.hash[:12]}...  parent={e.parent_hash[:12]}...")

    print(f"\nmerkle root (commitment to all 3): {led.merkle_root()[:24]}...")
    print(f"chain verifies: {led.verify()}")

    print("\n== now simulate tampering with history ==")
    led._conn.execute("UPDATE entries SET action = 'delete_everything' WHERE seq = 2")
    led._conn.commit()
    try:
        led.verify()
    except TamperError as exc:
        print(f"  caught the tamper -> {exc}")

    led.close()


if __name__ == "__main__":
    main()
