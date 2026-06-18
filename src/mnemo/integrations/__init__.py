"""Framework integrations.

A thin layer that lets existing agent frameworks (LangGraph, AutoGen, CrewAI, or
a plain function pipeline) gain Mnemosyne's guarantees by *wrapping* their nodes
rather than replacing the framework.

Public API:
    MnemoRuntime    governs `state -> update` nodes with record/replay + consensus
"""

from .adapter import MnemoRuntime

__all__ = ["MnemoRuntime"]
