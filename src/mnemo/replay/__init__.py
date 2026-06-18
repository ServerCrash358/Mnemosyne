"""Deterministic record/replay engine.

Records each agent's (inputs -> output) so a run can be replayed exactly from the
ledger without re-invoking the stochastic model. This is how non-determinism is
sidestepped for audit and reproduction.
"""
