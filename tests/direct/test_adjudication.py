"""Stage two: residual adjudication, and its binding to a specific mechanisation.

The second consensus round exists because some clauses genuinely cannot be
mechanised. What matters is that it is *narrow*: it only ever runs when the
mechanised half already passed, it is told the mechanised results as ground
truth, and its ruling is recorded against the policy digest it was decided
under.
"""

import json

import pytest

from conftest import FAITHFUL, GOOD, TOO_SHORT

COMPILE_PROMPT = r"compiling a rule"
RULE_PROMPT = r"ruling on the clauses"

# Clause 4 mechanised instead of residual, so the "nothing to adjudicate" branch
# is reachable. Still satisfies every acceptance vector.
FULLY_MECHANISED = {
    "clauses": FAITHFUL["clauses"][:3]
    + [
        {
            "id": "4",
            "kind": "mechanised",
            "effect": "require",
            "predicate": {"op": "len", "field": "body", "rel": "ge", "value": 1},
        }
    ]
}


def ruling(satisfied, overall=None, cid="4"):
    payload = {"rulings": [{"id": cid, "satisfied": satisfied, "reason": "because"}]}
    payload["overall"] = overall if overall is not None else ("PASS" if satisfied else "FAIL")
    return json.dumps(payload)


# ------------------------------------------------------------------ pre-checks
def test_cannot_adjudicate_before_compiling(direct_vm, policy):
    with direct_vm.expect_revert("not compiled"):
        policy.adjudicate(json.dumps(GOOD))


def test_a_mechanical_failure_is_never_sent_to_a_model(direct_vm, compiled):
    """A FAIL costs nothing: the deterministic engine already settled it, and a
    residual ruling must not be able to override a violated predicate."""
    with direct_vm.expect_revert("nothing to adjudicate"):
        compiled.adjudicate(json.dumps(TOO_SHORT))


def test_nothing_to_adjudicate_when_the_program_is_fully_mechanised(direct_vm, policy):
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FULLY_MECHANISED))
    policy.compile_policy()
    assert json.loads(policy.evaluate(json.dumps(GOOD)))["verdict"] == "PASS"
    with direct_vm.expect_revert("nothing to adjudicate"):
        policy.adjudicate(json.dumps(GOOD))


def test_invalid_payload_is_rejected_before_consensus(direct_vm, compiled):
    with direct_vm.expect_revert():
        compiled.adjudicate(json.dumps(dict(GOOD, surprise=1)))
    with direct_vm.expect_revert():
        compiled.adjudicate("{not json")

# --------------------------------------------------------------- the happy path
def test_a_satisfied_residual_clause_yields_pass(direct_vm, compiled):
    direct_vm.mock_llm(RULE_PROMPT, ruling(True))
    result = json.loads(compiled.adjudicate(json.dumps(GOOD)))

    assert result["verdict"] == "PASS"
    assert result["rulings"] == [{"id": "4", "satisfied": True}]
    assert result["stale"] is False
    assert result["policy_digest"] == json.loads(compiled.status())["policy_digest"]
    assert json.loads(compiled.status())["ruling_count"] == 1


def test_an_unsatisfied_residual_clause_yields_fail(direct_vm, compiled):
    direct_vm.mock_llm(RULE_PROMPT, ruling(False))
    result = json.loads(compiled.adjudicate(json.dumps(GOOD)))
    assert result["verdict"] == "FAIL"


def test_the_model_cannot_self_certify_the_aggregate(direct_vm, compiled):
    """The model is asked for an `overall` field and it is deliberately ignored:
    the verdict is recomputed from the per-clause rulings on chain."""
    direct_vm.mock_llm(RULE_PROMPT, ruling(False, overall="PASS"))
    result = json.loads(compiled.adjudicate(json.dumps(GOOD)))
    assert result["verdict"] == "FAIL"


# ------------------------------------------------------------------- coverage
@pytest.mark.parametrize(
    "response",
    [
        json.dumps({"rulings": [], "overall": "PASS"}),  # covers nothing
        json.dumps({"rulings": [{"id": "1", "satisfied": True}], "overall": "PASS"}),  # wrong clause
        json.dumps({"rulings": [{"id": "4", "satisfied": True}, {"id": "4", "satisfied": False}]}),  # duplicate
        json.dumps({"overall": "PASS"}),  # no rulings key at all
    ],
)
def test_rulings_must_cover_exactly_the_residual_clauses(direct_vm, compiled, response):
    direct_vm.mock_llm(RULE_PROMPT, response)
    with direct_vm.expect_revert():
        compiled.adjudicate(json.dumps(GOOD))
    assert json.loads(compiled.status())["ruling_count"] == 0


# ----------------------------------------------------------------- idempotency
def test_re_adjudicating_the_same_payload_is_a_no_op(direct_vm, compiled):
    """An appeal can re-execute a transaction. A second pass must return the
    recorded ruling rather than appending a duplicate."""
    direct_vm.mock_llm(RULE_PROMPT, ruling(True))
    first = json.loads(compiled.adjudicate(json.dumps(GOOD)))

    direct_vm.clear_mocks()  # no mock registered: a second LLM call would fail
    second = json.loads(compiled.adjudicate(json.dumps(GOOD)))

    assert second == first
    assert json.loads(compiled.status())["ruling_count"] == 1

# ------------------------------------------------------ validator on the ruling
def test_validator_agrees_on_an_identical_ruling(direct_vm, compiled):
    direct_vm.mock_llm(RULE_PROMPT, ruling(True))
    compiled.adjudicate(json.dumps(GOOD))
    assert direct_vm.run_validator() is True


def test_validator_rejects_a_flipped_ruling(direct_vm, compiled):
    """Comparative, with no tolerance: these are booleans about clauses, so an
    independent re-judgement that disagrees must reject."""
    direct_vm.mock_llm(RULE_PROMPT, ruling(True))
    compiled.adjudicate(json.dumps(GOOD))

    direct_vm.clear_mocks()
    direct_vm.mock_llm(RULE_PROMPT, ruling(False))
    assert direct_vm.run_validator() is False


def test_validator_rejects_a_malformed_leader_ruling(direct_vm, compiled):
    direct_vm.mock_llm(RULE_PROMPT, ruling(True))
    compiled.adjudicate(json.dumps(GOOD))
    assert direct_vm.run_validator(leader_result="{}") is False
    assert direct_vm.run_validator(leader_error=RuntimeError("[LLM_ERROR] junk")) is False


# ----------------------------------------------------------- digest binding
def test_a_ruling_does_not_survive_a_new_mechanisation(direct_vm, compiled):
    """The ruling was made about a specific compiled program. Recompiling means
    the question may no longer be the same question, so the old ruling must not
    keep authorising anything."""
    direct_vm.mock_llm(RULE_PROMPT, ruling(True))
    compiled.adjudicate(json.dumps(GOOD))
    assert json.loads(compiled.ruling_for(json.dumps(GOOD)))["verdict"] == "PASS"

    tighter = json.loads(json.dumps(FAITHFUL))
    tighter["clauses"][0]["predicate"]["value"] = 250
    direct_vm.clear_mocks()
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(tighter))
    compiled.compile_policy()

    # Same payload, new policy version: there is no ruling for it any more.
    assert json.loads(compiled.status())["policy_version"] == 2
    assert json.loads(compiled.ruling_for(json.dumps(GOOD)))["verdict"] == "NO_RULING"
    # The historical record is still there, and still marked with its own digest.
    assert json.loads(compiled.status())["ruling_count"] == 1


def test_ruling_for_reports_no_ruling_and_bad_payloads(compiled):
    assert json.loads(compiled.ruling_for(json.dumps(GOOD)))["verdict"] == "NO_RULING"
    assert json.loads(compiled.ruling_for("nope"))["verdict"] == "INVALID_PAYLOAD"
