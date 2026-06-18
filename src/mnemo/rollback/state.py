"""Prefix rollback by deterministic state reconstruction.

The ledger never erases history, so "rolling back to step N" does NOT mean
deleting entries N+1.. — it means *reconstructing* the system state as it was at
step N by replaying entries 0..N onto a fresh, empty state.

This is the event-sourcing idea: state is a *fold* (left reduction) over the log.
    state_N = reduce(reducer, entries[0..N], initial_state)
Because the fold is pure and the log is immutable, the same prefix always yields
the same state — which is the whole point of "deterministic state-replay."

The caller supplies a `reducer(state, entry) -> new_state` describing how each
transition mutates state. Mnemosyne stays domain-agnostic; the application knows
what its transitions mean.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Optional

from ..ledger import Entry, Ledger

Reducer = Callable[[Any, Entry], Any]


def rebuild_state(
    ledger: Ledger,
    reducer: Reducer,
    initial_state: Optional[Any] = None,
    up_to: Optional[int] = None,
) -> Any:
    """Reconstruct state by folding the reducer over entries 0..up_to (inclusive).

    `up_to=None` rebuilds the full current state; `up_to=N` rebuilds the state as
    it existed right after entry N — i.e. a rollback to that prefix.
    """
    # Deep-copy so the caller's initial_state is never mutated in place.
    state = copy.deepcopy(initial_state) if initial_state is not None else {}
    for entry in ledger:
        if up_to is not None and entry.seq > up_to:
            break
        state = reducer(state, entry)
    return state


def state_at(ledger: Ledger, reducer: Reducer, seq: int, initial_state=None) -> Any:
    """Convenience: the reconstructed state immediately after entry `seq`."""
    return rebuild_state(ledger, reducer, initial_state=initial_state, up_to=seq)
