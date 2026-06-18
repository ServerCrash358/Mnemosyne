# Roadmap

## Done (v2.1)

- [x] **Ledger** (`mnemo.ledger`) — hash chain + Merkle root + verify-prefix, SQLite WAL.
- [x] **Replay** (`mnemo.replay`) — record `(inputs -> output)`, replay with no model calls + divergence detection.
- [x] **Agents / swarm** (`mnemo.agents`) — A->B->C pipeline, every hop recorded.
- [x] **Rollback** (`mnemo.rollback`) — prefix reconstruction (event-sourcing fold) + saga compensation.
- [x] **Consensus** (`mnemo.consensus`) — BFT quorum + pluggable **verifier** and **normalizer**, `min_votes` override.
- [x] **Integration adapter** (`mnemo.integrations`) — govern any `state -> update` node; works on real LangGraph.
- [x] **Design spec** ([DESIGN.md](DESIGN.md)) — the citable finding.

## Next

1. **Scale hardening** (deferred from v2.1)
   - Parallel replicas with timeouts + early-quorum exit (latency = quorum-th fastest).
   - Thread-safe ledger appends.
   - Snapshotting -> O(tail) state reconstruction.
2. **Merkle inclusion proofs** — prove one entry belongs to a root in `log n`.
3. **Signed entries** — make tampering not just *detectable* but *attributable*.
4. **Real Claude-backed agents** — swap toy callables for model/tool replicas (diverse models for true independence).
5. **Full replay sandbox** — capture *all* nondeterminism (clock, RNG, retrieval, network), not just agent I/O.

## Open questions
- What counts as a deterministic "input snapshot"? (prompt + tools + retrieved docs + model id + params + seed)
- Detecting correlated (non-independent) replica failure — diversity metrics?
- For irreversible external actions: which need sagas vs. which can be gated behind consensus pre-commit?
