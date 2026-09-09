"""Mutation testing for the exact equivalence verifier.

A passing test suite proves the tests run. It does not prove they would notice
if the verifier were wrong -- and this verifier's whole job is to be a security
boundary, so "would we notice" is the question that matters.

Each mutation below is a small, plausible mistake in the proof machinery: an
off-by-one in the integer partition, a representative that does not represent
its class, a mis-derived containment lattice, a dropped effect, positional
clause matching, a one-sided comparison. Every one of them creates a FALSE
ACCEPT -- two behaviourally different programs certified as equivalent -- which
is exactly the failure the Portal reviewer objected to.

Usage:
    .venv/bin/python tools/mutation_check.py

The contract is mutated in place and restored in a `finally`, then the restore
is verified byte for byte. Nothing is left behind.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "compiled_policy.py"
PYTHON = ROOT / ".venv" / "bin" / "python"

# (name, what it breaks, old, new)
MUTATIONS = [
    (
        "int-boundary",
        "drops the below-the-minimum integer cell, so `n <= k` and `n == k` "
        "become indistinguishable",
        "    cells = [constants[0] - 1]  # below the minimum",
        "    cells = [constants[0]]  # MUTANT: below the minimum removed",
    ),
    (
        "str-representative",
        "the representative of a literal class no longer equals the literal, so "
        "no state ever satisfies an equality atom",
        "            reps.append(value)",
        "            reps.append(value + \"!\")  # MUTANT",
    ),
    (
        "contains-lattice",
        "substring closure computed in the wrong direction, so realisable "
        "containment classes are dropped and unrealisable ones enumerated",
        "            if i != j and patterns[i] in patterns[j]:",
        "            if i != j and patterns[j] in patterns[i]:  # MUTANT",
    ),
    (
        "effect-inversion",
        "clause satisfaction ignores `forbid`, so `require p` and `forbid p` "
        "look identical",
        "    return holds if clause[\"effect\"] == \"require\" else (not holds)",
        "    return holds  # MUTANT: effect ignored",
    ),
    (
        "clause-selection",
        "clauses matched by position instead of by immutable id",
        "            left[clause[\"id\"]] = clause",
        "            left[str(len(left))] = clause  # MUTANT: positional",
    ),
    (
        "one-sided-comparison",
        "only half of the disagreement is checked: B stricter than A passes",
        "            if _clause_satisfied(left[cid], state) != _clause_satisfied(right[cid], state):",
        "            if _clause_satisfied(left[cid], state) and not _clause_satisfied(right[cid], state):  # MUTANT",
    ),
]


def run_suite():
    """The whole default suite, exactly as CI runs it."""
    proc = subprocess.run(
        [str(PYTHON), "-m", "pytest", "-q", "-p", "no:randomly"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    failed = []
    for line in proc.stdout.splitlines():
        if line.startswith("FAILED ") or line.startswith("ERROR "):
            failed.append(line.split(" ")[1].split(" - ")[0])
    summary = [ln for ln in proc.stdout.splitlines() if " passed" in ln or " failed" in ln]
    return proc.returncode, failed, (summary[-1] if summary else "?")


def main():
    original = CONTRACT.read_text(encoding="utf-8")
    survivors = []
    try:
        for name, breaks, old, new in MUTATIONS:
            if original.count(old) != 1:
                print("!! %-22s SKIPPED: anchor matched %d times" % (name, original.count(old)))
                survivors.append(name)
                continue
            CONTRACT.write_text(original.replace(old, new), encoding="utf-8")
            code, failed, summary = run_suite()
            status = "CAUGHT " if code != 0 else "SURVIVED"
            print("%s %-22s %s" % (status, name, summary))
            print("         breaks: %s" % breaks)
            for test in failed[:6]:
                print("         - %s" % test)
            if len(failed) > 6:
                print("         - ... and %d more" % (len(failed) - 6))
            if code == 0:
                survivors.append(name)
            print()
    finally:
        CONTRACT.write_text(original, encoding="utf-8")

    clean = CONTRACT.read_text(encoding="utf-8") == original
    print("contract restored byte for byte: %s" % ("yes" if clean else "NO -- CHECK GIT"))
    if survivors:
        print("SURVIVING MUTANTS: %s" % ", ".join(survivors))
        return 1
    print("every mutation was caught")
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
