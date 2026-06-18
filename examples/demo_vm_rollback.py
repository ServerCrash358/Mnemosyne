"""Rolling back an irreversible action: deleting a VM.

You can't un-delete a VM by replaying a dict. The two defenses from the design
discussion, made concrete:

  DEFENSE 1 (prevent): the delete is gated behind BFT consensus, so a lone
            "nuke everything" agent never reaches quorum.

  DEFENSE 2 (compensate): a destructive action must capture a PRE-IMAGE
            (a snapshot) into the ledger BEFORE it executes. The saga compensator
            reads that snapshot id back out and recreates the resource.

The punchline at the end: without a captured pre-image, compensation can recreate
the VM shell but the disk contents are gone — which is why Defense 1 matters most.

Run:  python examples/demo_vm_rollback.py
"""

from mnemo.consensus import BFTConsensus
from mnemo.ledger import Ledger
from mnemo.rollback import SagaRegistry

# ---- a fake cloud we can actually mutate --------------------------------------
cloud = {"vm-42": {"spec": {"cpu": 4, "ram": 16}, "disk": "PRODUCTION DATA"}}
snapshots: dict = {}


def snapshot_vm(vm_id: str) -> str:
    """Capture a pre-image so the delete is reversible. Returns a snapshot id."""
    snap_id = f"snap-{vm_id}"
    snapshots[snap_id] = {k: dict(v) if isinstance(v, dict) else v
                          for k, v in cloud[vm_id].items()}
    return snap_id


def banner(t):
    print(f"\n{'=' * 4} {t} {'=' * 4}")


def main():
    ledger = Ledger()

    banner("DEFENSE 1: consensus gates the destructive action")
    # 3 honest agents agree to delete; 1 Byzantine agent wants to delete a
    # different (innocent) VM. The honest value reaches quorum; the liar can't.
    honest = lambda i: {"vm": "vm-42", "action": "delete"}
    liar = lambda i: {"vm": "vm-99-innocent", "action": "delete"}
    bft = BFTConsensus(ledger, [honest, honest, honest, liar], f=1)

    # Capture the pre-image BEFORE committing/executing the delete.
    target = "vm-42"
    snap_id = snapshot_vm(target)
    result = bft.propose(
        "infra",
        "delete_vm",
        {"vm": target, "snapshot_id": snap_id, "spec": cloud[target]["spec"]},
    )
    print(f"  quorum reached ({result.votes}/4); pre-image captured as {snap_id}")

    # Now actually perform the side-effect.
    del cloud[target]
    print(f"  executed delete -> cloud now: {dict(cloud)}")

    banner("DEFENSE 2: compensate (recreate from the snapshot)")
    saga = SagaRegistry()

    @saga.compensator("delete_vm")
    def undo_delete(entry):
        snap = entry.payload["inputs"]["snapshot_id"]
        vm = entry.payload["inputs"]["vm"]
        cloud[vm] = {k: dict(v) if isinstance(v, dict) else v
                     for k, v in snapshots[snap].items()}
        print(f"    compensating delete_vm: restored {vm} from {snap}")

    print("  a later step failed; rolling back the delete:")
    saga.compensate_to(ledger, target_seq=-1)
    print(f"  cloud after rollback: {dict(cloud)}")
    print(f"  disk contents recovered: {cloud['vm-42']['disk']!r}")

    banner("why Defense 1 matters: no pre-image = unrecoverable")
    print("  If we had deleted WITHOUT snapshotting first, the compensator could")
    print("  recreate an empty VM but never the disk data - no system can conjure")
    print("  deleted bytes back. Prevention (consensus gate) beats cure.")

    ledger.close()


if __name__ == "__main__":
    main()
