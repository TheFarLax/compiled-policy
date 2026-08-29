"""Deterministic behaviour of CompiledPolicy: the parts that involve no model.

Everything here runs in direct mode in milliseconds and would run identically on
every validator, which is the whole claim the primitive makes about `evaluate`.
"""

import json

import pytest

from conftest import (
    CLAUSES,
    FAITHFUL,
    GOOD,
    NO_TESTS,
    SCHEMA,
    TITLE,
    TOO_SHORT,
    VECTORS,
    WRONG_LANG,
)


def verdict(policy, payload):
    return json.loads(policy.evaluate(json.dumps(payload)))


# ------------------------------------------------------------------ constructor
def test_rule_is_stored_verbatim(policy):
    rule = json.loads(policy.rule())
    assert rule["title"] == TITLE
    assert [c["text"] for c in rule["clauses"]] == CLAUSES
    assert [c["id"] for c in rule["clauses"]] == ["1", "2", "3", "4"]
    assert rule["fields"] == SCHEMA
    assert len(rule["vectors"]) == len(VECTORS)

    status = json.loads(policy.status())
    assert status["compiled"] is False
    assert status["policy_version"] == 0
    assert status["frozen"] is False


@pytest.mark.parametrize(
    "bad_vectors",
    [
        [{"payload": GOOD, "expect": "PASS"}, {"payload": GOOD, "expect": "PASS"}],  # no FAIL case
        [{"payload": TOO_SHORT, "expect": "FAIL"}, {"payload": WRONG_LANG, "expect": "FAIL"}],  # no PASS
    ],
)
def test_vectors_must_contain_both_outcomes(deploy, direct_vm, bad_vectors):
    with direct_vm.expect_revert():
        deploy("compiled_policy.py", TITLE, json.dumps(CLAUSES), json.dumps(SCHEMA), json.dumps(bad_vectors))


def test_vector_payload_must_match_schema(deploy, direct_vm):
    broken = [
        {"payload": {"word_count": "five hundred", "language": "English", "has_tests": True, "body": "x"},
         "expect": "PASS"},
        {"payload": TOO_SHORT, "expect": "FAIL"},
    ]
    with direct_vm.expect_revert():
        deploy("compiled_policy.py", TITLE, json.dumps(CLAUSES), json.dumps(SCHEMA), json.dumps(broken))


def test_duplicate_field_rejected(deploy, direct_vm):
    dupes = SCHEMA + [{"name": "word_count", "kind": "int"}]
    with direct_vm.expect_revert():
        deploy("compiled_policy.py", TITLE, json.dumps(CLAUSES), json.dumps(dupes), json.dumps(VECTORS))


# ------------------------------------------------------- evaluate() before compile
def test_uncompiled_never_passes(policy):
    result = verdict(policy, GOOD)
    assert result["verdict"] == "UNCOMPILED"
    assert result["policy_version"] == 0


# --------------------------------------------------------- evaluate() verdicts
def test_mechanical_fail_is_cheap_and_names_the_clause(compiled):
    result = verdict(compiled, TOO_SHORT)
    assert result["verdict"] == "FAIL"
    assert result["violated"] == ["1"]

    result = verdict(compiled, WRONG_LANG)
    assert result["verdict"] == "FAIL"
    assert result["violated"] == ["2"]

    result = verdict(compiled, NO_TESTS)
    assert result["verdict"] == "FAIL"
    assert result["violated"] == ["3"]


def test_residual_required_is_a_refusal_not_a_pass(compiled):
    result = verdict(compiled, GOOD)
    assert result["verdict"] == "RESIDUAL_REQUIRED"
    assert result["residual"] == ["4"]
    assert result["violated"] == []
    # The distinction that matters: this is not PASS.
    assert result["verdict"] != "PASS"


def test_string_comparison_is_normalised(compiled):
    # Declared normalisation: casing and surrounding whitespace cannot dodge a
    # clause, and cannot spuriously fail one either.
    payload = dict(GOOD)
    payload["language"] = "  ENGLISH  "
    assert verdict(compiled, payload)["verdict"] == "RESIDUAL_REQUIRED"


@pytest.mark.parametrize(
    "payload,reason_fragment",
    [
        ({"word_count": 500, "language": "English", "has_tests": True}, "missing field"),
        (dict(GOOD, extra=1), "undeclared field"),
        (dict(GOOD, word_count=True), "must be an int"),
        (dict(GOOD, has_tests="yes"), "must be a bool"),
        (dict(GOOD, language=5), "must be a str"),
    ],
)
def test_invalid_payload_is_its_own_verdict(compiled, payload, reason_fragment):
    result = verdict(compiled, payload)
    assert result["verdict"] == "INVALID_PAYLOAD"
    assert reason_fragment in result["reason"]


def test_non_json_payload_is_invalid_not_a_crash(compiled):
    result = json.loads(compiled.evaluate("not json at all"))
    assert result["verdict"] == "INVALID_PAYLOAD"

# --------------------------------------------------------- digest and lifecycle
def test_forbid_inverts_the_predicate_end_to_end(direct_vm, policy):
    """`forbid` is the other half of the effect vocabulary and it inverts clause
    satisfaction, so a sign error here would silently authorise. Driven all the
    way through evaluate(), not just through a validator comparison.

    `forbid word_count < 200` must behave exactly like `require word_count >= 200`,
    including at the boundary: 199 violates, 200 does not."""
    forbidding = json.loads(json.dumps(FAITHFUL))
    forbidding["clauses"][0] = {
        "id": "1",
        "kind": "mechanised",
        "effect": "forbid",
        "predicate": {"op": "cmp", "field": "word_count", "rel": "lt", "value": 200},
    }
    direct_vm.mock_llm(r"compiling a rule", json.dumps(forbidding))
    policy.compile_policy()

    assert json.loads(policy.program())["clauses"][0]["effect"] == "forbid"

    # Below the bound: the forbidden predicate holds, so the clause is violated.
    low = verdict(policy, dict(GOOD, word_count=199))
    assert low["verdict"] == "FAIL"
    assert low["violated"] == ["1"]
    # At and above the bound: the forbidden predicate does not hold.
    assert verdict(policy, dict(GOOD, word_count=200))["verdict"] == "RESIDUAL_REQUIRED"
    assert verdict(policy, dict(GOOD, word_count=500))["verdict"] == "RESIDUAL_REQUIRED"
    # And a clause failing for another reason still reports its own id.
    assert verdict(policy, WRONG_LANG)["violated"] == ["2"]


def test_digest_is_stable_and_reported(compiled):
    status = json.loads(compiled.status())
    assert status["compiled"] is True
    assert status["policy_version"] == 1
    assert len(status["policy_digest"]) == 64
    # evaluate() echoes the digest so a consumer can pin the verdict to a
    # specific mechanisation.
    assert verdict(compiled, GOOD)["policy_digest"] == status["policy_digest"]


def test_only_owner_may_compile_or_freeze(direct_vm, policy, direct_alice):
    with direct_vm.prank(direct_alice):
        with direct_vm.expect_revert("only owner"):
            policy.compile_policy()
        with direct_vm.expect_revert("only owner"):
            policy.freeze()


def test_freeze_blocks_recompilation_but_not_reads(direct_vm, compiled):
    compiled.freeze()
    assert json.loads(compiled.status())["frozen"] is True
    with direct_vm.expect_revert("frozen"):
        compiled.compile_policy()
    # Reads keep working; freezing closes the compiler, not the gate.
    assert verdict(compiled, TOO_SHORT)["verdict"] == "FAIL"


def test_cannot_freeze_before_compiling(direct_vm, policy):
    with direct_vm.expect_revert("nothing to freeze"):
        policy.freeze()


def test_program_is_readable_only_once_admitted(direct_vm, policy):
    with direct_vm.expect_revert("not compiled"):
        policy.program()
