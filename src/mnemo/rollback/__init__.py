"""Rollback & compensation.

Given a target prefix in the ledger, restores the system to that state — either by
replaying the prefix onto a clean store, or by running compensating transactions
(sagas) for side-effects that cannot be literally undone.
"""
