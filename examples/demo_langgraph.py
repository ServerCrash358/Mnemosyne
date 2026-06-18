"""Govern a *real* LangGraph StateGraph with Mnemosyne.

This is the proof that the guarantees bolt onto a framework engineers already use,
without changing its control flow: you build a normal LangGraph graph, but each
node is wrapped with `rt.govern(...)`. Record once, then replay the compiled graph
deterministically over the same ledger.

Run:  pip install -e ".[langgraph]"   then   python examples/demo_langgraph.py
"""

from typing import TypedDict

from mnemo.integrations import MnemoRuntime
from mnemo.ledger import Ledger
from mnemo.replay import RECORD, REPLAY


class State(TypedDict, total=False):
    svc: str
    plan: str
    applied: str
    status: str


def build_graph(rt: MnemoRuntime):
    from langgraph.graph import END, START, StateGraph

    honest = lambda s: {"plan": "drain->restart"}
    liar = lambda s: {"plan": "delete-prod"}

    g = StateGraph(State)
    # A consensus-gated node (Byzantine replica outvoted) + two recorded nodes.
    g.add_node("decide", rt.govern("decide", replicas=[honest, honest, honest, liar], f=1))
    g.add_node("apply", rt.govern("apply", lambda s: {"applied": s["plan"]}))
    g.add_node("report", rt.govern("report", lambda s: {"status": f"done: {s['applied']}"}))
    g.add_edge(START, "decide")
    g.add_edge("decide", "apply")
    g.add_edge("apply", "report")
    g.add_edge("report", END)
    return g.compile()


def main():
    try:
        import langgraph  # noqa: F401
    except Exception as exc:
        print(f"LangGraph not available ({exc}).")
        print("Install with:  pip install -e \".[langgraph]\"")
        print("The framework-agnostic equivalent runs via: python examples/demo_integration.py")
        return

    ledger = Ledger()

    print("== RECORD: run the LangGraph graph, governed by Mnemosyne ==")
    rec_app = build_graph(MnemoRuntime(ledger, mode=RECORD))
    recorded = rec_app.invoke({"svc": "checkout"})
    print(f"  result: {recorded.get('status')}")
    print(f"  committed {len(ledger)} transitions; ledger verifies: {ledger.verify()}")

    print("\n== REPLAY: same graph, served from the ledger (nodes don't execute) ==")
    rep_app = build_graph(MnemoRuntime(ledger, mode=REPLAY))
    replayed = rep_app.invoke({"svc": "checkout"})
    print(f"  replayed result: {replayed.get('status')}")
    print(f"  identical to recorded: {replayed.get('status') == recorded.get('status')}")

    ledger.close()


if __name__ == "__main__":
    main()
