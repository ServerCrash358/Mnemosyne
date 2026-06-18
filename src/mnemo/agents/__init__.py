"""Agent & swarm orchestration.

Wraps individual agents and wires the swarm graph (Agent A -> B -> C). Each agent
action is captured as a transition proposed to the ledger (via the replay engine).

Public API:
    Agent       a named (inputs -> output) step
    Swarm       chains agents into a recorded/replayable pipeline
"""

from .agent import Agent
from .swarm import Swarm

__all__ = ["Agent", "Swarm"]
