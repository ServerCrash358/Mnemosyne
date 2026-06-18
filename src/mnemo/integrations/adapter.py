"""Framework adapter: govern any `state -> update` node.

The adoption story for Mnemosyne is *not* "rewrite your swarm in our framework."
It's "keep LangGraph / AutoGen / CrewAI, wrap your nodes, gain the guarantees."

Almost every graph framework models a node as a function from state to a (partial)
state update. `MnemoRuntime.govern` wraps such a function so that each call is:

  - RECORD mode, no replicas : run the node, append (inputs, output) to the ledger.
  - RECORD mode, with replicas: run BFT consensus over the replicas; commit the
                                agreed (verified, normalized) output to the ledger.
  - REPLAY mode              : return the recorded output for this step WITHOUT
                                running the node, asserting the inputs still match.

The wrapped callable keeps the exact `state -> update` signature, so it drops
straight into the host framework's `add_node(...)`. Running the same wrapped graph
with `mode=REPLAY` reproduces a past execution deterministically.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Union

from ..consensus import BFTConsensus
from ..ledger import Ledger, fingerprint
from ..replay import RECORD, REPLAY, DivergenceError

NodeFn = Callable[[dict], Any]
# replicas may be an explicit list of derivations, or an int N meaning "run the
# node fn N times" (convenient, but correlated — prefer diverse callables).
Replicas = Union[int, List[NodeFn]]


class MnemoRuntime:
    """Holds the ledger + mode and hands out governed node wrappers.

    One runtime governs one workflow execution. Create it in RECORD mode to
    capture a run; create it in REPLAY mode over the *same* ledger to reproduce
    that run. Replay assumes nodes are invoked in their recorded order (true for
    linear / deterministically-ordered graphs).
    """

    def __init__(self, ledger: Optional[Ledger] = None, mode: str = RECORD) -> None:
        if mode not in (RECORD, REPLAY):
            raise ValueError(f"mode must be {RECORD!r} or {REPLAY!r}")
        self.ledger = ledger if ledger is not None else Ledger()
        self.mode = mode
        self._cursor = 0  # next ledger seq to serve during replay

    def govern(
        self,
        node_id: str,
        fn: Optional[NodeFn] = None,
        *,
        replicas: Optional[Replicas] = None,
        f: int = 1,
        verifier=None,
        normalize=None,
        min_votes: Optional[int] = None,
    ) -> Callable:
        """Wrap a node. Usable directly or as a decorator.

            graph.add_node("plan", rt.govern("plan", plan_fn))

            @rt.govern("plan")
            def plan(state): ...
        """

        def wrap(node_fn: NodeFn) -> NodeFn:
            def governed(state: dict) -> Any:
                inputs = dict(state)  # snapshot the inputs we record/compare on

                if self.mode == REPLAY:
                    return self._replay(node_id, inputs)

                # RECORD
                if replicas is not None:
                    reps = self._resolve_replicas(replicas, node_fn)
                    bft = BFTConsensus(
                        self.ledger,
                        reps,
                        f=f,
                        normalize=normalize,
                        verifier=verifier,
                        min_votes=min_votes,
                    )
                    # propose() appends the agreed output to the ledger itself.
                    return bft.propose(node_id, "node", inputs).output

                output = node_fn(inputs)
                self.ledger.append(
                    node_id,
                    "node",
                    {"input_fp": fingerprint(inputs), "inputs": inputs, "output": output},
                )
                return output

            governed.__name__ = f"governed::{node_id}"
            return governed

        if fn is not None:
            return wrap(fn)
        # A list of replicas fully defines the node, so no fn is needed — return
        # the governed node directly. With no fn and no list replicas, return the
        # decorator form (the fn, and any int-replica fan-out, arrive later).
        if isinstance(replicas, (list, tuple)):
            return wrap(None)
        return wrap

    # ----- internals -----------------------------------------------------------

    @staticmethod
    def _resolve_replicas(replicas: Replicas, node_fn: NodeFn) -> List[NodeFn]:
        if isinstance(replicas, int):
            # N copies of the same fn: convenient for demos, but the derivations
            # are correlated. Pass diverse callables for real Byzantine coverage.
            return [node_fn] * replicas
        return list(replicas)

    def _replay(self, node_id: str, inputs: dict) -> Any:
        if self._cursor >= len(self.ledger):
            raise DivergenceError(
                f"replay ran past the recording at node {node_id!r} "
                f"(no entry at seq={self._cursor})"
            )
        entry = self.ledger.get(self._cursor)
        self._cursor += 1
        # Compare against the recorded inputs (works whether the entry was written
        # by the simple path or by consensus — both store "inputs").
        if fingerprint(entry.payload["inputs"]) != fingerprint(inputs):
            raise DivergenceError(
                f"replay diverged at seq={entry.seq} (node {node_id!r}): "
                f"live inputs != recorded inputs"
            )
        return entry.payload["output"]
