"""Deterministic record/replay engine.

This is the module that actually tames LLM non-determinism. The trick is simple
and powerful: **don't try to make the model deterministic — record what it did,
then replay the recording.**

Two modes:

  RECORD  call the real (stochastic) function, capture its output into the
          ledger alongside a fingerprint of the inputs, return the output.

  REPLAY  do NOT call the function. Walk the recorded entries in order, hand
          back each stored output, and assert the inputs still match. If a
          replayed input diverges from what was recorded, the run has drifted
          and we stop loudly instead of silently producing a different history.

Because every step is keyed to the ledger, a replay reproduces a past run bit
for bit — which is what makes audit, debugging, and rollback possible at all.
"""

from __future__ import annotations

from typing import Any, Callable

from ..ledger import Entry, Ledger, fingerprint

RECORD = "record"
REPLAY = "replay"

# What an agent step looks like: a function from an input dict to an output dict.
StepFn = Callable[[dict], Any]


class DivergenceError(Exception):
    """Raised in REPLAY mode when live inputs differ from what was recorded.

    This is the canary for the "small divergence at step 2 cascades by step 20"
    problem in the project brief: we catch the drift at the exact step it occurs.
    """


class ReplayEngine:
    def __init__(self, ledger: Ledger, mode: str = RECORD) -> None:
        if mode not in (RECORD, REPLAY):
            raise ValueError(f"mode must be {RECORD!r} or {REPLAY!r}")
        self.ledger = ledger
        self.mode = mode
        self._cursor = 0  # seq of the next recorded entry to replay

    def step(self, actor: str, action: str, inputs: dict, fn: StepFn) -> Any:
        """Run (or replay) one agent step.

        In RECORD mode this is a transparent wrapper around `fn`. In REPLAY mode
        `fn` is never invoked — its recorded output is returned instead.
        """
        fp = fingerprint(inputs)

        if self.mode == RECORD:
            output = fn(inputs)
            self.ledger.append(
                actor,
                action,
                {"input_fp": fp, "inputs": inputs, "output": output},
            )
            return output

        # REPLAY
        entry = self._next_recorded()
        if entry.payload["input_fp"] != fp:
            raise DivergenceError(
                f"replay diverged at seq={entry.seq} ({actor}/{action}): "
                f"live input fingerprint {fp[:12]}... != "
                f"recorded {entry.payload['input_fp'][:12]}..."
            )
        return entry.payload["output"]

    def _next_recorded(self) -> Entry:
        if self._cursor >= len(self.ledger):
            raise DivergenceError(
                f"replay ran past the recording (no entry at seq={self._cursor})"
            )
        entry = self.ledger.get(self._cursor)
        self._cursor += 1
        return entry
