"""Compensation (the Saga pattern) for side-effects you can't replay away.

State reconstruction (`state.py`) handles everything *inside* the system. But
agents also cause **external** effects — a server was drained, an email was sent,
a VM was deleted. You can't un-send an email by rebuilding a dict. The standard
answer from distributed systems is a *compensating transaction*: for each forward
action, register the action that semantically undoes it, and to roll back, run
the compensators in reverse order.

    forward:    drain_traffic -> restart -> scale_up
    compensate: scale_down  <- (none)   <- restore_traffic     (reverse order)

This gives Mnemosyne the "atomic-ish" rollback the brief asks for: if an agent
fails halfway through a multi-step remediation, we can walk the ledger backward
and undo the steps that already happened.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from ..ledger import Entry, Ledger

Compensator = Callable[[Entry], None]


class SagaRegistry:
    """Maps an action name to the function that compensates (undoes) it."""

    def __init__(self) -> None:
        self._compensators: Dict[str, Compensator] = {}

    def compensator(self, action: str) -> Callable[[Compensator], Compensator]:
        """Decorator to register a compensator for a given action.

            @saga.compensator("scale_up")
            def undo_scale_up(entry): ...
        """

        def register(fn: Compensator) -> Compensator:
            self._compensators[action] = fn
            return fn

        return register

    def compensate_to(self, ledger: Ledger, target_seq: int) -> List[Entry]:
        """Undo every entry after `target_seq`, newest first.

        Returns the list of entries that were compensated (in the order they were
        undone). Entries whose action has no registered compensator are treated
        as having no external effect and are skipped.

        Running newest-first matters: you must reverse the *last* thing you did
        before the thing before it, or you'd undo into an inconsistent order.
        """
        to_undo = [e for e in ledger if e.seq > target_seq]
        undone: List[Entry] = []
        for entry in reversed(to_undo):
            comp = self._compensators.get(entry.action)
            if comp is not None:
                comp(entry)
                undone.append(entry)
        return undone
