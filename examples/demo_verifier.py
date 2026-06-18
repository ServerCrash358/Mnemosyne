"""Verifier-first consensus on a real task: "solve this integral".

This is the worked example behind the v2.0 changes. It shows the full pipeline:

    derive  ->  VERIFY (differentiate & check)  ->  NORMALIZE (canonical form)  ->  VOTE

Two ideas made concrete:

  1. NORMALIZE: agents return the SAME answer in different spellings
     ("x**2/2 + C", "0.5*x**2 + C", "x*x/2 + C"). Raw strings differ, so they'd
     never vote together. SymPy collapses them to one canonical form first.

  2. VERIFY: the source of truth is NOT the vote. We differentiate each proposed
     antiderivative and check it equals the integrand. A confident-but-wrong
     majority is rejected by this oracle no matter how many agents agree.

Run:  python examples/demo_verifier.py   (requires sympy:  pip install -e ".[examples]")
"""

import sympy

from mnemo.consensus import BFTConsensus, NoQuorumError
from mnemo.ledger import Ledger

x, C = sympy.symbols("x C")


def parse(expr_str: str):
    # rational=True turns 0.5 into the exact Rational 1/2, so float vs fraction
    # spellings canonicalize identically.
    return sympy.sympify(expr_str, locals={"x": x, "C": C}, rational=True)


def normalize_integral(out: dict) -> dict:
    """Canonical form of an antiderivative, used only for vote comparison."""
    return {"answer": str(sympy.expand(parse(out["answer"])))}


def make_integral_verifier(integrand_str: str):
    """Oracle: an answer is correct iff d/dx(answer) == integrand."""
    integrand = parse(integrand_str)

    def verify(inputs, out):
        derivative = sympy.diff(parse(out["answer"]), x)
        return sympy.simplify(derivative - integrand) == 0

    return verify


def banner(t):
    print(f"\n{'=' * 4} {t} {'=' * 4}")


def main():
    # ---- Scenario A: correct answers in different spellings + one hallucination
    banner("A. integral of x dx  (correct = x**2/2 + C)")
    integrand = "x"
    replicas_A = [
        lambda i: {"answer": "x**2/2 + C"},   # correct
        lambda i: {"answer": "0.5*x**2 + C"}, # correct, float spelling
        lambda i: {"answer": "x*x/2 + C"},    # correct, yet another spelling
        lambda i: {"answer": "x**3 + C"},     # WRONG (hallucination)
    ]

    print("  naive voting (no normalize, no verify):")
    try:
        BFTConsensus(Ledger(), replicas_A, f=1).propose("solver", "integrate",
                                                        {"integrand": integrand})
    except NoQuorumError as e:
        print(f"    -> {e}")
        print("    (every spelling is a different string, so nobody agrees)")

    print("  verifier-first (verify -> normalize -> vote):")
    bft = BFTConsensus(
        Ledger(),
        replicas_A,
        f=1,
        normalize=normalize_integral,
        verifier=make_integral_verifier(integrand),
    )
    res = bft.propose("solver", "integrate", {"integrand": integrand})
    print(f"    -> committed '{res.output['answer']}' "
          f"with {res.votes} votes, {res.rejected} rejected by the oracle")
    print("    (3 correct spellings normalized to one value; the wrong one was")
    print("     differentiated, found != x, and discarded)")

    # ---- Scenario B: the majority is confidently WRONG
    banner("B. integral of 2*x dx  (correct = x**2 + C) - wrong majority")
    integrand = "2*x"
    replicas_B = [
        lambda i: {"answer": "x + C"},      # WRONG (d/dx = 1)
        lambda i: {"answer": "x + C"},      # WRONG
        lambda i: {"answer": "x + C"},      # WRONG  <- 3-vote majority!
        lambda i: {"answer": "x**2 + C"},   # the lone CORRECT answer
    ]

    print("  pure voting would commit the wrong 'x + C' (3 of 4 votes).")
    print("  verifier-first, trusting the oracle (min_votes=1):")
    bft = BFTConsensus(
        Ledger(),
        replicas_B,
        f=1,
        normalize=normalize_integral,
        verifier=make_integral_verifier(integrand),
        min_votes=1,  # a sound oracle makes a single verified answer sufficient
    )
    res = bft.propose("solver", "integrate", {"integrand": integrand})
    print(f"    -> committed '{res.output['answer']}' "
          f"({res.rejected} confidently-wrong answers rejected)")
    print("    SOURCE OF TRUTH = differentiation, not the vote.")


if __name__ == "__main__":
    main()
