# Mnemosyne (`mnemo`)

**A transactional safety layer for multi-agent LLM systems** — deterministic
replay, cryptographic provenance, verifier-gated consensus, and prefix rollback.

> Named for the Greek Titaness of memory and perfect recall.

Mnemosyne is **not another agent framework.** It's a thin layer you wrap around
the framework you already use (LangGraph, AutoGen, CrewAI, or a plain function
pipeline) so that every agent action becomes an auditable, reproducible,
reversible, trust-gated transaction.

---

## Why

LLM agents are stochastic. In a single-agent loop a human reviews each step, so
that's fine. In a **swarm** — where Agent A's output feeds B, which shapes C's
tool call — non-determinism *compounds*: a small divergence at step 2 cascades
into a completely different system state by step 20, with no record of how you
got there.

Existing frameworks orchestrate agents but provide **no transactional
guarantees**. An agent can begin a multi-step action, fail halfway, and leave the
system partially mutated — with no rollback. That "it might make things worse"
risk is the core barrier to autonomy in high-stakes settings (cloud remediation
today; physical/robotic control later).

## What you get

Four guarantees, beyond what plain Raft-style "did a majority agree?" offers:

| Guarantee | What it means |
|-----------|---------------|
| **Provenance** | Cryptographically prove the *exact sequence* of state transitions that produced the current state. Any tampering is detectable. |
| **Replay** | Reproduce any past run *byte-for-byte* from the ledger — with **zero** model/tool calls (so you don't re-charge cards or re-send emails while debugging). |
| **Rollback** | Restore the system to *any prefix* of the sequence: rebuild internal state by replay, and undo external side-effects via compensation. |
| **Trust gating** | Commit a transition only when it clears a configurable bar — a **verifier** and/or a Byzantine-tolerant **quorum** — so a confidently-wrong agent can't act unilaterally. |

## The one idea to take away

> **Consensus yields *agreement*, not *truth*.**

Agents sharing a model fail in correlated ways, so "5 of 5 agreed" can be the same
mistake five times. Mnemosyne makes truth come from *outside* the swarm — a
**verifier** (e.g. differentiate an integral and check it), **genuinely
independent** replicas, **reality** (the real cloud/API state), or a **human**.
What Mnemosyne guarantees is *accountability and reversibility*, not omniscience.

## Show me

```python
from mnemo.integrations import MnemoRuntime
from mnemo.replay import RECORD, REPLAY

rt = MnemoRuntime(mode=RECORD)

# A cheap, safe step: just record it to the tamper-evident ledger.
plan = rt.govern("plan", lambda state: {"plan": "drain -> restart"})

# A risky decision: gate it behind Byzantine-tolerant consensus (N = 3f+1
# replicas) plus a verifier. A 'delete-prod' hallucination gets outvoted —
# or, where an oracle exists, rejected outright regardless of votes.
decide = rt.govern(
    "decide",
    replicas=[agent_a, agent_b, agent_c, agent_d],   # f = 1  ->  needs 3 to agree
    verifier=lambda inputs, output: is_safe(output),
)

state = plan({"svc": "checkout"})
state = {**state, **decide(state)}        # committed to the ledger

# Later — reproduce the whole run deterministically, no agents execute:
replay_rt = MnemoRuntime(rt.ledger, mode=REPLAY)
# ...rebuild the same graph with replay_rt and re-run it...
```

The wrapped node keeps the framework's `state -> update` contract, so it drops
straight into `graph.add_node(...)`. See [`examples/demo_langgraph.py`](examples/demo_langgraph.py)
for the same thing on a real LangGraph graph.

## How a transition flows

```
propose
   │   derive    run N independent replicas (candidate outputs)
   │   verify    drop provably-wrong outputs (when an oracle exists)
   │   normalize collapse equivalent outputs to a canonical form
   │   vote      require a quorum (default 2f+1) to agree
   ▼   commit    append the agreed output to the hash-chained ledger
 ledger ──► replay (reproduce)  /  rollback (rebuild prefix + compensate)
```

## Architecture

| Module | Responsibility |
|--------|----------------|
| `mnemo.ledger` | Append-only, hash-chained, Merkle-committed log on SQLite (WAL). The provenance store. |
| `mnemo.replay` | Record `(inputs -> output)`; replay with no model calls; detect divergence. |
| `mnemo.agents` | Minimal swarm (A → B → C); every hop becomes a recorded transition. |
| `mnemo.rollback` | Prefix reconstruction (event-sourcing fold) + saga compensation for side-effects. |
| `mnemo.consensus` | Byzantine-tolerant commit with pluggable **verifier** + **normalizer**. |
| `mnemo.integrations` | The adapter: govern any `state -> update` node, framework-agnostic. |

Core has **no third-party dependencies** — just the Python standard library
(`hashlib`, `sqlite3`, `json`). Demos pull optional extras.

## Install & run

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows (use source on *nix)
pip install -e ".[dev,examples]"
pytest                                              # 41 tests
```

Then take the guided tour of the demos — see **[examples/README.md](examples/README.md)**.
Quick taste:

```bash
python examples/demo_full.py        # consensus -> ledger -> replay -> rollback, end to end
python examples/demo_verifier.py    # a wrong majority overruled by a verifier (integral oracle)
python examples/demo_integration.py # govern a pipeline, then replay it with no execution
```

## A note on the cost of consensus

Gating a transition behind `N = 3f+1` replicas means **N model calls per gated
step** — for `f=1`, that's ~4× the API cost of a single call. The code (and the
adapter's per-node control) is designed so you pay that only where it's worth it:

- **Gate selectively** — use plain record/replay for cheap/safe nodes; reserve
  consensus for risky/irreversible ones.
- **Prefer a verifier to more replicas** — one generation + a cheap check beats
  four generations when an oracle exists.
- **Mix model tiers** — cheaper models for replicas, the strong one for the verifier.

(The library itself makes no API calls; the bundled agents are plain functions,
so running the tests and demos costs nothing.)

## Documentation

- **[docs/DESIGN.md](docs/DESIGN.md)** — the full specification: the four
  guarantees stated precisely, the consensus theory (BFT vs Raft, the N-version
  reframe, the source-of-truth hierarchy), the threat model, *proven vs assumed*,
  and a per-component **scaling path**. **Start here** to understand or cite the work.
- **[docs/ROADMAP.md](docs/ROADMAP.md)** — what's done and what's next.
- **[examples/README.md](examples/README.md)** — a tour of the runnable demos.

## Status

`v2.1` — five core modules + framework adapter + design spec. 41 passing tests,
six runnable demos. Reference implementation, not yet production-hardened (see the
scaling path in the design doc).

## License

See [LICENSE](LICENSE).
