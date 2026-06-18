"""Agents: the unit of work in a swarm.

An `Agent` is intentionally thin — just an id plus a callable `inputs -> output`.
The callable can wrap anything: a deterministic function, a tool call, or a real
LLM API request. Mnemosyne doesn't care what's inside; it only cares that every
invocation flows through the replay engine so it lands in the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Agent:
    """A named step in the swarm.

    `id` identifies the actor in the ledger; `fn` is the work it performs.
    Frozen so an agent's identity can't shift mid-run.
    """

    id: str
    fn: Callable[[dict], Any]
