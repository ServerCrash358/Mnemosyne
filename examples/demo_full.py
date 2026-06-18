"""End-to-end tour of Mnemosyne: consensus -> ledger -> replay -> rollback.

Scenario: an agent swarm remediates a sick cloud service. We show all five
guarantees working together:

  1. BFT consensus   gate each transition behind a 2f+1 quorum (reject a liar)
  2. Provenance      every committed transition lands in a hash-chained ledger
  3. Verification    the whole chain is cryptographically verifiable
  4. Replay          reproduce the run with zero re-execution
  5. Rollback        reconstruct an earlier state + compensate side-effects

Run:  python examples/demo_full.py
"""

from mnemo.consensus import BFTConsensus, NoQuorumError
from mnemo.ledger import Ledger
from mnemo.rollback import SagaRegistry, rebuild_state, state_at


def banner(title):
    print(f"\n{'=' * 4} {title} {'=' * 4}")


# --- a domain reducer: how each transition mutates the service's state ---------
def svc_reducer(state, entry):
    new = dict(state)
    new.update(entry.payload.get("output", {}).get("state", {}))
    return new


def main():
    ledger = Ledger()

    banner("1. BFT consensus gates each transition")
    # 3 honest replicas + 1 Byzantine 'liar' that wants to do something dangerous.
    def plan(i):    return {"step": "drain",   "state": {"traffic": "drained"}}
    def execute(i): return {"step": "restart", "state": {"status": "restarting"}}
    def verify(i):  return {"step": "healthy", "state": {"status": "healthy"}}
    def liar(i):    return {"step": "nuke",    "state": {"status": "deleted"}}

    steps = [("planner", plan), ("executor", execute), ("verifier", verify)]
    for actor, honest_fn in steps:
        bft = BFTConsensus(ledger, [honest_fn, honest_fn, honest_fn, liar], f=1)
        res = bft.propose(actor, honest_fn.__name__, {"svc": "checkout"})
        print(f"  {actor:9} committed '{res.output['step']}' "
              f"with {res.votes}/4 votes (liar outvoted)")

    banner("2 & 3. Provenance ledger is intact & verifiable")
    for e in ledger:
        print(f"  seq={e.seq} {e.actor:9} hash={e.hash[:10]}... "
              f"parent={e.parent_hash[:10]}...")
    print(f"  merkle root: {ledger.merkle_root()[:24]}...")
    print(f"  chain verifies: {ledger.verify()}")

    banner("4. Deterministic replay (no re-execution)")
    final = rebuild_state(ledger, svc_reducer)
    after_step1 = state_at(ledger, svc_reducer, seq=0)
    print(f"  state after step 0: {after_step1}")
    print(f"  final state:        {final}")

    banner("5. Rollback via compensation")
    saga = SagaRegistry()

    @saga.compensator("execute")
    def undo_restart(entry):
        print("    compensating: restart -> rolled back to previous binary")

    @saga.compensator("plan")
    def undo_drain(entry):
        print("    compensating: drain -> traffic restored")

    print("  a later step failed; rolling back everything after seq=-1:")
    undone = saga.compensate_to(ledger, target_seq=-1)
    print(f"  compensated {len(undone)} side-effecting steps (newest first)")

    banner("what a Byzantine majority looks like")
    bad_ledger = Ledger()
    bft = BFTConsensus(bad_ledger, [plan, plan, liar, liar], f=1)
    try:
        bft.propose("planner", "plan", {"svc": "checkout"})
    except NoQuorumError as exc:
        print(f"  refused to commit -> {exc}")
    print(f"  ledger stayed empty: {len(bad_ledger) == 0}")

    ledger.close()


if __name__ == "__main__":
    main()
