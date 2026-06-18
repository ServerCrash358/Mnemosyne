"""Deterministic record/replay engine.

Records each agent's (inputs -> output) into the ledger so a run can be replayed
exactly without re-invoking the stochastic model. This is how non-determinism is
sidestepped for audit and reproduction.

Public API:
    ReplayEngine        record/replay wrapper around agent steps
    RECORD, REPLAY      the two modes
    DivergenceError     raised when a replay drifts from its recording
"""

from .engine import RECORD, REPLAY, DivergenceError, ReplayEngine

__all__ = ["ReplayEngine", "RECORD", "REPLAY", "DivergenceError"]
