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

`v0.1` — all five core modules implemented, with 31 passing tests and two
runnable demos. See [docs/ROADMAP.md](docs/ROADMAP.md) for what's next
(inclusion proofs, real LLM/tool agents, multi-process replicas).

## Quick start

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -e ".[dev]"
pytest                                # 31 tests
python examples/demo_ledger.py        # hash chain + tamper detection
python examples/demo_full.py          # consensus -> ledger -> replay -> rollback
```
