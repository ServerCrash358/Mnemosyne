"""Rollback & compensation.

Two complementary strategies for restoring a system to an earlier prefix:

  - rebuild_state / state_at  : reconstruct internal state by replaying a prefix
                                of the immutable log (event sourcing).
  - SagaRegistry              : undo *external* side-effects via compensating
                                transactions, in reverse order.

Public API:
    rebuild_state, state_at, Reducer
    SagaRegistry, Compensator
"""

from .saga import Compensator, SagaRegistry
from .state import Reducer, rebuild_state, state_at

__all__ = [
    "rebuild_state",
    "state_at",
    "Reducer",
    "SagaRegistry",
    "Compensator",
]
