# Build order

A suggested sequence — each layer is usable before the next exists.

1. **Ledger first** (`mnemo.ledger`)
   - Append-only log entry: `{seq, parent_hash, payload, hash}`
   - Hash chain + Merkle root; verify-prefix function.
   - Back it with SQLite (real WAL).

2. **Replay** (`mnemo.replay`)
   - Record `(agent_id, inputs) -> output` into the ledger.
   - Replay a run from the ledger with no model calls; assert identical state.

3. **Agents / swarm** (`mnemo.agents`)
   - Minimal A->B->C graph (can build on LangGraph or roll our own).
   - Every action becomes a proposed transition.

4. **Rollback** (`mnemo.rollback`)
   - Rebuild state at prefix N by replaying entries `0..N`.
   - Saga/compensation hooks for external side-effects.

5. **Consensus** (`mnemo.consensus`)
   - Start with single-node "commit". Then multi-replica.
   - Add BFT voting: N replicas re-derive a transition; commit only on quorum.

## Open questions to resolve while building
- What counts as a deterministic "input snapshot" for an agent? (prompt + tools + retrieved docs + seed)
- How do we detect a Byzantine agent — re-run on k replicas and compare hashes?
- For irreversible external actions, which need sagas vs. which can be gated behind consensus pre-commit?
