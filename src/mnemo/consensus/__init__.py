"""Byzantine fault-tolerant consensus layer.

Decides agreement on the *next* committed state transition. Unlike plain Raft
(crash faults), this tolerates Byzantine faults — i.e. an agent that returns
confidently-wrong output rather than simply crashing.
"""
