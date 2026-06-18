# Examples — a guided tour

Each script is **executable documentation**: it runs end to end and prints what
it's proving. Run them from the project root after `pip install -e ".[examples]"`.

Suggested order: `demo_ledger` → `demo_full` → `demo_verifier` →
`demo_vm_rollback` → `demo_integration` → `demo_langgraph`.

| Demo | Shows | Extra deps |
|------|-------|-----------|
| [`demo_ledger.py`](demo_ledger.py) | The provenance ledger: a hash-chained log, a Merkle commitment, and tamper detection (we corrupt an entry and `verify()` catches it). | none |
| [`demo_full.py`](demo_full.py) | The whole pipeline on a cloud-remediation scenario: BFT consensus gates each step (a Byzantine "nuke" replica is outvoted) → entries land in the ledger → chain verifies → state is replayed → side-effects are compensated. | none |
| [`demo_verifier.py`](demo_verifier.py) | **Verify → normalize → vote** on "solve this integral." Equivalent answers (`x**2/2 + C` vs `0.5*x**2 + C`) are canonicalized so they vote together, and a *confident wrong majority* is overruled by differentiating the answer. The punchline: **source of truth = the verifier, not the vote.** | `sympy` (`.[examples]`) |
| [`demo_vm_rollback.py`](demo_vm_rollback.py) | Rolling back an **irreversible** action (deleting a VM): consensus gates the delete, a pre-image snapshot is captured *before* executing, and a saga compensator recreates the VM from it. Ends by explaining why prevention beats cure. | none |
| [`demo_integration.py`](demo_integration.py) | The adapter on a plain function pipeline: wrap `state -> update` nodes, record a run (one consensus-gated node + two plain ones), then **replay it with the node bodies guaranteed not to execute**. | none |
| [`demo_langgraph.py`](demo_langgraph.py) | The same adapter on a **real LangGraph `StateGraph`** — proof the guarantees bolt onto a framework engineers already use, without changing its control flow. Records, then replays the compiled graph deterministically. | `langgraph` (`.[langgraph]`) |

## What to look for

- **`demo_ledger`** — note that editing any past entry changes its hash and
  `verify()` raises `TamperError`. That's the provenance guarantee.
- **`demo_verifier`** — Scenario B has 3 of 4 agents confidently wrong; the
  verifier still produces the correct answer. This is the core "agreement ≠ truth"
  lesson, runnable.
- **`demo_integration` / `demo_langgraph`** — the replay run reproduces the
  recorded result while the node functions never run. That's deterministic replay
  with zero model/tool calls.

## Run all (quick check)

```bash
python examples/demo_ledger.py
python examples/demo_full.py
python examples/demo_verifier.py
python examples/demo_vm_rollback.py
python examples/demo_integration.py
pip install -e ".[langgraph]" && python examples/demo_langgraph.py
```
