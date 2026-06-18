"""Govern a plain function pipeline (no framework required).

Shows the adapter wrapping ordinary `state -> update` nodes so a workflow gets
record/replay + consensus for free. The same wrapping works on any framework
whose nodes follow that contract (LangGraph/AutoGen/CrewAI) — see
demo_langgraph.py for the real-framework version.

Run:  python examples/demo_integration.py
"""

from mnemo.integrations import MnemoRuntime
from mnemo.ledger import Ledger
from mnemo.replay import RECORD, REPLAY


def run_pipeline(nodes, state):
    for node in nodes:
        state = {**state, **node(state)}
    return state


def banner(t):
    print(f"\n{'=' * 4} {t} {'=' * 4}")


def main():
    ledger = Ledger()

    banner("RECORD a run (one consensus-gated node + two plain nodes)")
    rt = MnemoRuntime(ledger, mode=RECORD)

    # A consensus-gated decision: 3 honest replicas + 1 Byzantine 'liar'.
    honest = lambda s: {"plan": "drain->restart"}
    liar = lambda s: {"plan": "delete-prod"}

    nodes = [
        rt.govern("decide", replicas=[honest, honest, honest, liar], f=1),
        rt.govern("apply", lambda s: {"applied": s["plan"]}),
        rt.govern("report", lambda s: {"status": f"done: {s['applied']}"}),
    ]
    result = run_pipeline(nodes, {"svc": "checkout"})
    print(f"  result: {result['status']}")
    print(f"  ledger length: {len(ledger)}, verifies: {ledger.verify()}")
    print("  (the 'delete-prod' replica was outvoted 3-to-1 and never committed)")

    banner("REPLAY the same run (no node bodies execute)")
    rt_replay = MnemoRuntime(ledger, mode=REPLAY)

    def must_not_run(name):
        def _f(s):
            raise AssertionError(f"node {name} should not execute during replay")
        return _f

    replay_nodes = [
        rt_replay.govern("decide", must_not_run("decide")),
        rt_replay.govern("apply", must_not_run("apply")),
        rt_replay.govern("report", must_not_run("report")),
    ]
    replayed = run_pipeline(replay_nodes, {"svc": "checkout"})
    print(f"  replayed result: {replayed['status']}")
    print(f"  identical to recorded: {replayed == result}")

    ledger.close()


if __name__ == "__main__":
    main()
