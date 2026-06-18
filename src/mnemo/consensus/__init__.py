"""Byzantine fault-tolerant consensus layer.

Decides agreement on the *next* committed state transition. Unlike plain Raft
(crash faults), this tolerates Byzantine faults — i.e. an agent that returns
confidently-wrong output rather than simply crashing. A transition is committed
to the ledger only when >= 2f+1 of 3f+1 replicas agree on it.

Public API:
    BFTConsensus    runs a transition across replicas and commits on quorum
    CommitResult    what a successful commit returns
    Vote            one replica's fingerprinted output
    NoQuorumError   raised when agreement can't be reached (commit nothing)
"""

from .bft import BFTConsensus, CommitResult, NoQuorumError, Vote

__all__ = ["BFTConsensus", "CommitResult", "Vote", "NoQuorumError"]
