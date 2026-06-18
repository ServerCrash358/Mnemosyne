"""Swarm orchestration: chaining agents into a pipeline.

This is the smallest interesting topology from the project brief — Agent A's
output becomes Agent B's input, which shapes Agent C. It's exactly where
non-determinism compounds, so it's exactly where we want every hop recorded.

`Swarm.run` threads data through the agents in order, sending each agent's output
into the next agent as input. Crucially, it does NOT call the agents directly: it
calls `engine.step(...)`, so in RECORD mode every hop is appended to the ledger,
and in REPLAY mode the whole pipeline reproduces from the recording without
touching the (stochastic) agent bodies at all.
"""

from __future__ import annotations

from typing import List

from ..replay import ReplayEngine
from .agent import Agent


class Swarm:
    def __init__(self, agents: List[Agent], engine: ReplayEngine) -> None:
        self.agents = agents
        self.engine = engine

    def run(self, initial_input: dict) -> dict:
        """Execute the pipeline, returning the final agent's output.

        The same call works for both recording a fresh run and replaying a past
        one — the only difference is the mode the engine was constructed with.
        """
        data = initial_input
        for agent in self.agents:
            data = self.engine.step(agent.id, "invoke", data, agent.fn)
        return data
