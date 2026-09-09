"""The exact objection this redesign answers, reproduced as a test.

    "Validators compare independent programs on a capped sample of payloads,
     but different programs can agree on every sampled payload and still return
     conflicting PASS/FAIL results for an untested combination of field values."

Below is such a pair, for the running example rule. To prove the claim rather
than assert it, the DELETED probe generator is reproduced verbatim and run: it
really does produce identical verdict vectors for two programs that really do
return conflicting verdicts for a payload it never constructs.

The frozen copy is a specimen, not shared code. It is here so the test can show
what was wrong; nothing in `contracts/` imports it, and `test_no_probe_fallback`
in the direct suite asserts the contract carries no trace of it.
"""

import json

import pytest

from harness import cp

FIELDS = {"word_count": "int", "language": "str", "has_tests": "bool", "body": "str"}

GOOD = {"word_count": 500, "language": "English", "has_tests": True, "body": "a thorough writeup"}
TOO_SHORT = {"word_count": 10, "language": "English", "has_tests": True, "body": "brief"}
WRONG_LANG = {"word_count": 500, "language": "French", "has_tests": True, "body": "bon travail"}
SEED_PAYLOADS = [GOOD, TOO_SHORT, WRONG_LANG]


def rule_program(clause_one):
    """The running example with clause 1 swapped, canonicalised the way the
    contract canonicalises it."""
    return cp._canon_program(
        {
            "clauses": [
                clause_one,
                {"id": "2", "kind": "mechanised", "effect": "require",
                 "predicate": {"op": "cmp", "field": "language", "rel": "eq", "value": "English"}},
                {"id": "3", "kind": "mechanised", "effect": "require",
                 "predicate": {"op": "cmp", "field": "has_tests", "rel": "eq", "value": True}},
                {"id": "4", "kind": "residual"},
            ]
        }
    )


def mechanised(predicate, effect="require", cid="1"):
    return {"id": cid, "kind": "mechanised", "effect": effect, "predicate": predicate}


AT_LEAST_200 = {"op": "cmp", "field": "word_count", "rel": "ge", "value": 200}

# Identical to `AT_LEAST_200` everywhere except at exactly 300 words.
HOLED_AT_300 = {
    "op": "and",
    "args": [
        AT_LEAST_200,
        {"op": "not", "args": [{"op": "cmp", "field": "word_count", "rel": "eq", "value": 300}]},
    ],
}

# Widened, but only where clause 3 already fails, so the WHOLE-PROGRAM verdict is
# identical on every payload in existence -- no probe set of any size could
# separate these two by comparing verdicts.
WIDENED_UNDER_A_FAILING_CLAUSE = {
    "op": "or",
    "args": [AT_LEAST_200, {"op": "cmp", "field": "has_tests", "rel": "eq", "value": False}],
}

HONEST = rule_program(mechanised(AT_LEAST_200))
HOLED = rule_program(mechanised(HOLED_AT_300))
MASKED = rule_program(mechanised(WIDENED_UNDER_A_FAILING_CLAUSE))


# --------------------------------------------- the deleted probe generator
def _legacy_collect_candidates(program, fields, out):
    stack = [c["predicate"] for c in program["clauses"] if c["kind"] == "mechanised"]
    while stack:
        node = stack.pop()
        op = node["op"]
        if op in ("and", "or", "not"):
            stack.extend(node["args"])
            continue
        bucket = out.setdefault(node["field"], [])
        kind = fields[node["field"]]
        if op == "cmp":
            if kind == "int":
                for delta in (-1, 0, 1):
                    bucket.append(node["value"] + delta)
            else:
                bucket.append(node["value"])
        elif op == "in":
            for value in node["values"]:
                bucket.append(value)
                if kind == "int":
                    bucket.append(value + 1)
        elif op == "contains":
            bucket.append(node["value"])
            bucket.append(node["value"] + " tail")


def legacy_probe_payloads(fields, programs, seed_payloads, cap=96):
    candidates = {}
    for program in programs:
        _legacy_collect_candidates(program, fields, candidates)
    for name, kind in fields.items():
        bucket = candidates.setdefault(name, [])
        if kind == "bool":
            bucket.extend([True, False])
        unique_values = {}
        for value in bucket:
            unique_values[cp._canon(value)] = value
        candidates[name] = [unique_values[key] for key in sorted(unique_values.keys())]

    base = {n: (0 if k == "int" else ("" if k == "str" else False)) for n, k in fields.items()}
    probes = list(seed_payloads) + [dict(base)]
    names = sorted(fields.keys())
    for name in names:
        for value in candidates[name]:
            probe = dict(base)
            probe[name] = value
            probes.append(probe)
    widest = max(len(candidates[name]) for name in names)
    for index in range(min(widest, 8)):
        probe = dict(base)
        for name in names:
            if candidates[name]:
                probe[name] = candidates[name][index % len(candidates[name])]
        probes.append(probe)

    unique, seen = [], []
    for probe in probes:
        key = cp._canon(probe)
        if key not in seen:
            seen.append(key)
            unique.append(probe)
        if len(unique) >= cap:
            break
    return unique


def legacy_verdict_vector(program, probes):
    return [cp._eval_program(program, probe)["verdict"] for probe in probes]


# ============================================================== the objection
def test_the_probe_mechanism_could_not_separate_two_conflicting_programs():
    """The vulnerability, demonstrated end to end on the deleted code.

    Note what the probe set actually did: it DID try word_count == 300, twice.
    Both times with has_tests False, where clause 3 already fails, so both
    programs returned FAIL and the difference was invisible. Adding probes would
    not have helped; the sampling strategy simply never paired 300 with the
    field values that expose it."""
    probes = legacy_probe_payloads(FIELDS, [HONEST, HOLED], SEED_PAYLOADS)

    assert legacy_verdict_vector(HONEST, probes) == legacy_verdict_vector(HOLED, probes), (
        "the specimen is only meaningful if the old mechanism really did accept it"
    )

    tried_300 = [p for p in probes if p["word_count"] == 300]
    assert tried_300, "the old probe set did generate 300..."
    assert all(not p["has_tests"] for p in tried_300), "...but never with has_tests True"

    separating = dict(GOOD, word_count=300)
    assert separating not in probes
    assert cp._eval_program(HONEST, separating)["verdict"] == "RESIDUAL_REQUIRED"
    assert cp._eval_program(HOLED, separating)["verdict"] == "FAIL"


def test_the_exact_verifier_rejects_what_the_probe_set_admitted():
    """The same pair, decided by the replacement. THE test for this redesign."""
    assert cp._prove_equivalent(HONEST, HOLED, FIELDS) is False
    assert cp._prove_equivalent(HONEST, HONEST, FIELDS) is True


def test_a_difference_masked_by_another_clause_is_caught():
    """A stronger version of the same failure, and the reason the proof is
    per-clause rather than per-verdict.

    Clause 1 is widened to accept any submission without tests -- but clause 3
    already rejects those, so the whole-program verdict is identical for EVERY
    payload, not merely for sampled ones. No verdict-vector comparison of any
    size could ever have caught this. The reported `violated` list differs, and
    so does the meaning of clause 1."""
    for word_count in range(-5, 600):
        for language in ("English", "French", ""):
            for has_tests in (True, False):
                payload = {"word_count": word_count, "language": language,
                           "has_tests": has_tests, "body": ""}
                assert (
                    cp._eval_program(HONEST, payload)["verdict"]
                    == cp._eval_program(MASKED, payload)["verdict"]
                )

    hidden = {"word_count": 10, "language": "English", "has_tests": False, "body": ""}
    assert cp._eval_program(HONEST, hidden)["violated"] == ["1", "3"]
    assert cp._eval_program(MASKED, hidden)["violated"] == ["3"]

    probes = legacy_probe_payloads(FIELDS, [HONEST, MASKED], SEED_PAYLOADS)
    assert legacy_verdict_vector(HONEST, probes) == legacy_verdict_vector(MASKED, probes)

    assert cp._prove_equivalent(HONEST, MASKED, FIELDS) is False


def test_the_specimens_are_legal_programs_that_pass_every_public_gate():
    """Neither specimen is caught by an earlier layer, which is what made this a
    consensus problem rather than a validation problem."""
    clause_ids = ["1", "2", "3", "4"]
    vectors = [(GOOD, "PASS"), (TOO_SHORT, "FAIL"), (WRONG_LANG, "FAIL")]
    for program in (HONEST, HOLED, MASKED):
        cp._validate_program(program, FIELDS, clause_ids)
        cp._check_vectors(program, vectors)
        cp._check_provable(program, FIELDS)
