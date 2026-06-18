# Mnemosyne — Design & Specification

**A transactional layer for multi-agent LLM systems: deterministic replay,
cryptographic provenance, verifier-gated consensus, and prefix rollback.**

Status: reference specification + reference implementation (`mnemo` v2.x).
This document is the *finding*; the code under `src/mnemo/` is a reference
implementation that proves it, not a production system.

---

## 1. Problem

LLMs are stochastic: the same prompt at temperature > 0 yields different outputs.
In a single-agent loop a human reviews each step, so this is tolerable. In a
**multi-agent swarm** — Agent A's output feeds B, which shapes C's tool call —
the non-determinism *compounds*: a small divergence at step 2 cascades into a
completely different system state by step 20, with no record of how you got
there.

Current frameworks (LangGraph, AutoGen, CrewAI) orchestrate agents but provide
**no transactional guarantees**. An agent can begin a multi-step action, fail
halfway, and leave the system partially mutated, with no rollback. In
high-stakes settings (cloud remediation today, physical/robotic control later)
that "could make things worse" risk is the core barrier to autonomy.

## 2. Goals and non-goals

**Goals**

- **G1 Provenance** — cryptographically prove the exact sequence of state
  transitions that produced the current state.
- **G2 Determinism** — reproduce any past run exactly, without re-invoking the
  stochastic model.
- **G3 Atomicity / rollback** — restore the system to any prefix of the
  sequence, including undoing external side-effects where possible.
- **G4 Trust gating** — commit a transition only when it clears a configurable
  bar (verifier and/or quorum), tolerating agents that are confidently wrong.

**Non-goals**

- Making the LLM itself deterministic (impossible in general; we record instead).
- Manufacturing truth from agreement (see §8 — consensus yields agreement, not
  truth).
- A new agent framework. Mnemosyne is a *layer* that wraps existing ones (§13).

## 3. The four guarantees (precise statements)

1. **Tamper-evident history.** Given the ledger, any alteration of any committed
   entry is detectable: `verify()` recomputes the hash chain and fails on the
   first inconsistent link. (Integrity, not secrecy.)
2. **Deterministic replay.** Re-running a recorded workflow in REPLAY mode yields
   byte-identical outputs at every step, with zero model/tool invocations, or
   raises `DivergenceError` at the exact step that drifts.
3. **Prefix reconstruction.** For any `k`, the internal state after step `k` is
   `fold(reducer, entries[0..k])` and is reproducible from the immutable log.
4. **Gated commit.** A transition reaches the ledger only if it passes the
   configured `verifier` (if any) and gathers `>= threshold` agreeing votes;
   otherwise nothing is committed and the caller is told to escalate.

## 4. Architecture

```
            propose(transition)
                  │
                  ▼
        ┌───────────────────┐   derive on N replicas (parallel)
        │     consensus     │   verify  → filter provably-wrong
        │   (BFTConsensus)  │   normalize→ canonical form
        └─────────┬─────────┘   vote     → require quorum
                  │ agreed output
                  ▼
        ┌───────────────────┐   append-only, hash-chained,
        │      ledger       │   Merkle-committed, SQLite-WAL
        └─────────┬─────────┘
        replay ◄──┤──► rollback
   (reproduce a   │   (rebuild_state to prefix k;
    past run)     │    saga compensation for side-effects)
                  ▼
            agents / swarm  (A → B → C, every hop recorded)
```

Modules: `ledger`, `replay`, `agents`, `rollback`, `consensus`, plus
`integrations` (the framework adapter, §13).

## 5. Transition lifecycle

Each agent action is one transition:

```
derive → verify → normalize → vote → commit → (later: replay / rollback)
```

- **derive**: N independent replicas produce candidate outputs.
- **verify**: drop outputs that fail a domain oracle (when one exists).
- **normalize**: map each surviving output to a canonical form for comparison.
- **vote**: tally canonical forms; require `threshold` (default `2f+1`) agreement.
- **commit**: append the agreed output to the ledger (extends the hash chain).
- **replay/rollback**: reproduce or unwind using the committed log.

## 6. Data model

An `Entry` is immutable:

```
seq          monotonic position, 0-based
timestamp    unix seconds (recorded fact, part of the hash)
actor        agent id / "system"
action       short label
payload      JSON-serializable transition data
parent_hash  hash of entry seq-1 (genesis: 64 zeros)
hash         SHA-256 over canonical(seq,timestamp,actor,action,payload,parent_hash)
```

- **Hash chain**: `parent_hash` binds each entry to its predecessor → any edit to
  history breaks every subsequent hash (tamper-evidence, G1).
- **Canonicalization**: hashing is over canonical JSON (sorted keys, no
  whitespace) so equal values always produce equal bytes. The *same* principle
  generalizes to the consensus normalizer (§8).
- **Merkle root**: a single commitment over all entry hashes, so replicas can
  compare one 32-byte value instead of streaming the whole log; `log n`
  inclusion proofs are a planned extension.

## 7. Determinism via record/replay

We do **not** try to make the model deterministic. We record `(inputs, output)`
for every step. In REPLAY mode the recorded output is returned and the function
is never called — which simultaneously (a) reproduces stochastic outputs and
(b) prevents re-execution of side-effects (you don't re-charge a card or re-send
an email while debugging). A fingerprint of the live inputs is compared to the
recorded inputs; mismatch raises `DivergenceError` at that step. (Analogy: a game
replay file stores *moves*, not video — but because the LLM "engine" is
non-deterministic and side-effecting, we must record outputs too, not just
inputs.)

## 8. Consensus: agreement, not truth

**Why not Raft.** Raft tolerates *crash* faults: a node returns the right answer
or none. A hallucinating agent returns a confident, well-formed, *wrong* answer —
a **Byzantine** fault. BFT's rule: tolerate `f` such faults with `N = 3f+1`
replicas, committing on `>= 2f+1` agreement.

**Reframe for AI.** Our "replicas" are not distrustful network nodes; they are
*independent re-derivations* of the same transition (N model calls, ideally
diverse models/prompts). So in practice this is **N-version generation + voting +
verification**, which is the AI-appropriate reading of BFT.

**The hard truth.** Voting yields **agreement, not truth.** Agents sharing a
model fail in *correlated* ways, so 5/5 agreement can be 5× the same mistake —
which violates BFT's independence assumption. Therefore:

> Truth must be anchored *outside* the swarm.

Source-of-truth hierarchy (strongest first):

1. **Verifier / oracle** — where checking is cheaper than solving (integral →
   differentiate and compare; code → run tests; SQL → execute). A verified output
   is correct regardless of votes; voting becomes a tiebreaker.
2. **Engineered diversity** — different models/prompts/tools so faults are
   actually independent and the quorum math means something.
3. **Human-in-the-loop** — for unverifiable, high-stakes, irreversible actions;
   "no quorum → escalate (with provenance)" is a feature.
4. **Reality** — for infra, the authoritative cloud/API state, reconciled before
   and after acting.

This is why `BFTConsensus` takes pluggable `verifier` and `normalize`, and a
`min_votes` override (lower it only when backed by a sound verifier).

## 9. Rollback

- **Internal state**: event sourcing. `state_k = fold(reducer, entries[0..k])`.
  Pure fold over an immutable log ⇒ deterministic reconstruction (G3). We never
  delete history; "rollback" rebuilds an earlier state.
- **External side-effects**: the Saga pattern. Register a compensator per action;
  to roll back, run compensators newest-first. **Pre-image rule:** a destructive
  action must record the data needed to reverse it (e.g. a snapshot id) *before*
  executing. No pre-image ⇒ unrecoverable, which is why destructive actions
  should also be *gated* (§8) and staged (soft-delete) — prevention beats cure.

## 10. Threat / fault model

Defended:

- Post-hoc tampering or silent edits of history (hash chain).
- Up to `f` Byzantine replicas per transition, given `N >= 3f+1` and
  *independent* faults.
- Confidently-wrong outputs, when a sound verifier exists.
- Partial multi-step failure (rollback + compensation).

Assumed / out of scope (current reference impl):

- Faults are independent (correlated model errors defeat pure voting — mitigate
  with diversity + verifiers).
- The ledger host is trusted and not concurrently corrupted at the storage layer;
  integrity is *detectable*, not *prevented*, and entries are not yet signed.
- Single-node ledger; no network adversary between distributed replicas yet.
- Compensators are correct and idempotent (the app's responsibility).

## 11. Proven vs assumed

- **Demonstrated by tests/demos**: tamper detection; deterministic replay without
  re-execution; prefix reconstruction; quorum commit; Byzantine minority
  outvoted; verifier overriding a wrong majority; snapshot-based compensation.
- **Assumed / not yet built**: cross-node Byzantine agreement over a real
  network; signed entries; replicated/sharded log; exhaustive side-effect
  sandboxing for replay.

## 12. Scaling path (prototype → production)

| Component  | Reference impl            | Production direction |
|------------|---------------------------|----------------------|
| Ledger     | single-node SQLite (WAL)  | thread-safe writer + replicated/sharded log; snapshots & log compaction; blob store for large payloads; signed entries |
| Consensus  | in-process callables, serial | parallel replicas with timeouts & early-quorum exit; remote replicas (RPC); signed votes; view-change for a faulty coordinator |
| Replay     | records agent I/O         | sandbox *all* nondeterminism: tool calls, clock, RNG, retrieval, network |
| Rollback   | saga registry + reducer   | durable compensator log, idempotency keys, partial-failure recovery |
| Determinism| input-fingerprint check   | full content-addressed inputs incl. model id, params, retrieved context |

## 13. Integration model

Mnemosyne is a **layer**, not a framework. The adapter (`mnemo.integrations`)
wraps any node of the form `state -> update` so each invocation is recorded
(record/replay) and optionally consensus-gated, then committed to the ledger —
without changing the host framework's control flow.

```python
rt = MnemoRuntime(mode=RECORD)
graph.add_node("plan",    rt.govern("plan", plan_fn))                 # record/replay
graph.add_node("act",     rt.govern("act", replicas=[a, b, c, d],    # consensus-gated
                                     verifier=check, normalize=canon))
```

The same wrapped graph, run with `mode=REPLAY`, reproduces a past execution.
This is the adoption path: engineers keep LangGraph/AutoGen/CrewAI and gain the
four guarantees by wrapping nodes.

## 14. Public API (summary)

- `ledger`: `Ledger`, `Entry`, `verify`, `verify_prefix`, `merkle_root`,
  `fingerprint`, `TamperError`.
- `replay`: `ReplayEngine`, `RECORD`, `REPLAY`, `DivergenceError`.
- `agents`: `Agent`, `Swarm`.
- `rollback`: `rebuild_state`, `state_at`, `SagaRegistry`.
- `consensus`: `BFTConsensus(ledger, replicas, f, normalize, verifier,
  min_votes)`, `CommitResult`, `NoQuorumError`.
- `integrations`: `MnemoRuntime`, `govern`.

## 15. Roadmap

Merkle inclusion proofs · signed entries · parallel/remote replicas ·
real Claude-backed agents · full side-effect sandbox for replay ·
LangGraph/AutoGen adapters hardened.
