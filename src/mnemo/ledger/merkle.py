"""Merkle tree utilities.

The hash chain (in `entry.py`) already makes history tamper-evident. A Merkle
tree adds a second, complementary property: it reduces an entire list of entries
to ONE root hash, such that:

  - any change to any entry changes the root, and
  - you can later prove a single entry belongs to that root WITHOUT revealing or
    re-hashing the whole list (an "inclusion proof", added in step 2).

So the hash chain answers "is the sequence intact end-to-end?" and the Merkle
root answers "here is one 32-byte commitment to everything so far" — handy for
the consensus layer, where replicas compare a single root instead of the full
log.
"""

from __future__ import annotations

import hashlib
from typing import List

# Root of an empty tree. Arbitrary but fixed, so "no entries" hashes the same way
# everywhere.
EMPTY_ROOT = "0" * 64


def _hash_pair(left: str, right: str) -> str:
    """Hash two child node digests into their parent digest."""
    return hashlib.sha256((left + right).encode("utf-8")).hexdigest()


def merkle_root(leaf_hashes: List[str]) -> str:
    """Fold a list of leaf hashes up into a single Merkle root.

    Algorithm (a balanced binary hash tree):
      1. Start with the leaves (here, each entry's own hash).
      2. Pair them up and hash each pair into a parent node.
      3. If a level has an odd count, duplicate the last node so it can pair
         with itself — a standard convention that keeps the tree binary.
      4. Repeat until one node remains: the root.

    The tree has height ~log2(n), so verifying or proving membership later costs
    log(n) hashes instead of n — the whole reason to use a tree over a flat hash.
    """
    if not leaf_hashes:
        return EMPTY_ROOT

    level = list(leaf_hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])  # duplicate the lone node at this level
        level = [_hash_pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]
