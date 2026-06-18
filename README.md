# Mnemosyne (`mnemo`)

**Deterministic state-replay & Byzantine fault-tolerant consensus for multi-agent swarms.**

> Named for the Greek Titaness of memory and perfect recall.

## The problem

LLM agents are stochastic. In a single-agent workflow that's manageable. In a
**swarm** — where Agent A's output feeds B, which shapes C's tool call —
non-determinism compounds: a small divergence at step 2 cascades into a totally
different system state by step 20, with no audit trail of how you got there.

Existing frameworks (LangGraph, AutoGen, CrewAI) have **no transactional
atomicity**. An agent can fail halfway through a series of actions and leave the
system partially mutated, with no rollback. That risk is the core barrier to
deploying autonomous agents in high-stakes systems (cloud remediation, and
eventually physical domains like surgical robotics).

## What Mnemosyne guarantees

Beyond "did a majority agree on the state?" (plain Raft), Mnemosyne answers:

1. **Provenance** — cryptographically prove the *exact sequence* of state
   transitions that led to the current state.
2. **Replay** — deterministically reproduce any run from the ledger without
   re-invoking the stochastic model.
3. **Rollback** — restore the system to *any prefix* of that sequence.
4. **BFT consensus** — tolerate agents that return confidently-wrong output, not
   just agents that crash.

## Architecture (modules)

| Module                  | Responsibility |
|-------------------------|----------------|
| `mnemo.agents`          | Wrap agents & wire the swarm graph; emit transitions |
| `mnemo.consensus`       | Byzantine fault-tolerant agreement on the next transition |
| `mnemo.ledger`          | Hash-chained, Merkle-rooted write-ahead log (provenance) |
| `mnemo.replay`          | Record/replay engine for deterministic reproduction |
| `mnemo.rollback`        | Prefix rollback + compensating transactions (sagas) |

## Status

`v2.0` — all five core modules, **verifier-first consensus**, 35 passing tests,
four runnable demos.

What v2.0 adds over the first cut:

- **Pluggable normalizer** on `BFTConsensus` — collapses equivalent outputs to a
  canonical form before voting, so `x**2/2 + C` and `0.5*x**2 + C` vote together.
- **Pluggable verifier** — an oracle that filters to *provably-correct* outputs
  *before* voting. Where a sound oracle exists, it is the real source of truth and
  voting is demoted to a tiebreaker. Pipeline:
  `derive -> verify -> normalize -> vote -> commit`.
- **Snapshot-based compensation** for irreversible actions (the VM-delete case):
  capture a pre-image into the ledger before executing, recreate from it on
  rollback.

Key principle made explicit: **voting yields agreement, not truth.** Truth must
come from outside the swarm — a verifier, genuinely independent replicas, reality,
or a human. Mnemosyne provides accountability and reversibility, not omniscience.

See [docs/ROADMAP.md](docs/ROADMAP.md) for what's next (inclusion proofs, real
LLM/tool agents, multi-process replicas).

## Quick start

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -e ".[dev,examples]"
pytest                                # 35 tests
python examples/demo_ledger.py        # hash chain + tamper detection
python examples/demo_full.py          # consensus -> ledger -> replay -> rollback
python examples/demo_verifier.py      # verify -> normalize -> vote (integral oracle)
python examples/demo_vm_rollback.py   # gate + snapshot compensation for a VM delete
```
