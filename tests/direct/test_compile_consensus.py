"""Stage one: admitting a mechanisation, and how a validator checks the leader.

These tests are the point of the project. `direct_vm.run_validator()` replays the
captured validator closure, so we can prove -- not assert in prose -- that the
validator accepts an equivalent compilation and rejects a subtly wrong one.
"""

import json

import pytest

from conftest import FAITHFUL, GOOD, TOO_SHORT

COMPILE_PROMPT = r"compiling a rule"


def clause(cid, kind="mechanised", **rest):
    base = {"id": cid, "kind": kind}
    base.update(rest)
    return base


def program_with(cid, replacement):
    """FAITHFUL with one clause swapped out."""
    out = json.loads(json.dumps(FAITHFUL))
    out["clauses"] = [replacement if c["id"] == cid else c for c in out["clauses"]]
    return out


def word_count_clause(rel, value, effect="require"):
    return clause("1", effect=effect, predicate={"op": "cmp", "field": "word_count", "rel": rel, "value": value})


# --------------------------------------------------------------- the happy path
def test_faithful_program_is_admitted(direct_vm, policy):
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    admitted = json.loads(policy.compile_policy())

    ids = [c["id"] for c in admitted["clauses"]]
    assert ids == ["1", "2", "3", "4"]
    kinds = {c["id"]: c["kind"] for c in admitted["clauses"]}
    assert kinds == {"1": "mechanised", "2": "mechanised", "3": "mechanised", "4": "residual"}

    status = json.loads(policy.status())
    assert status["policy_version"] == 1
    assert status["compiled"] is True


def test_canonicalisation_makes_the_digest_shape_independent(direct_vm, policy):
    """Two compilations that differ only in the order of `and` operands must
    canonicalise to the same program.

    Proved without needing two deployments: admit one ordering, then offer the
    other. If canonicalisation works the digest is unchanged, so the contract
    must refuse it as an identical program rather than bumping the version."""
    left = {"op": "cmp", "field": "word_count", "rel": "ge", "value": 200}
    right = {"op": "cmp", "field": "language", "rel": "eq", "value": "English"}

    def merged(args):
        out = json.loads(json.dumps(FAITHFUL))
        out["clauses"] = [
            clause("1", effect="require", predicate={"op": "and", "args": args}),
            clause("2", kind="residual", question="Is the language acceptable to a reader?"),
            out["clauses"][2],
            out["clauses"][3],
        ]
        return out

    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(merged([left, right])))
    policy.compile_policy()
    first = json.loads(policy.status())["policy_digest"]

    direct_vm.clear_mocks()
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(merged([right, left])))
    with direct_vm.expect_revert("identical program"):
        policy.compile_policy()

    assert json.loads(policy.status())["policy_digest"] == first
    assert json.loads(policy.status())["policy_version"] == 1


# ------------------------------------------------------- validator: agreement
def test_validator_agrees_with_an_identical_compilation(direct_vm, policy):
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()
    assert direct_vm.run_validator() is True


def test_validator_agrees_with_a_differently_shaped_but_equivalent_program(direct_vm, policy):
    """`require word_count >= 200` and `require not(word_count < 200)` are the
    same rule written two ways. A validator that compared text, digests or JSON
    shape would reject this; behavioural comparison accepts it."""
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()

    inverted = program_with(
        "1",
        clause(
            "1",
            effect="require",
            predicate={"op": "not", "args": [{"op": "cmp", "field": "word_count", "rel": "lt", "value": 200}]},
        ),
    )
    direct_vm.clear_mocks()
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(inverted))
    assert direct_vm.run_validator() is True


def test_validator_agrees_when_effect_is_flipped_consistently(direct_vm, policy):
    """`require x >= 200` == `forbid x < 200`. Same behaviour, opposite effect."""
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()

    forbidden = program_with("1", word_count_clause("lt", 200, effect="forbid"))
    direct_vm.clear_mocks()
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(forbidden))
    assert direct_vm.run_validator() is True

# ---------------------------------------------------- validator: disagreement
def test_validator_rejects_a_threshold_the_acceptance_vectors_cannot_catch(direct_vm, policy):
    """The most important test in the suite.

    `word_count >= 150` satisfies every acceptance vector: the FAIL vector has
    10 words and still fails, the PASS vector has 500 and still passes. Only a
    behavioural comparison against an independent compilation notices that the
    two programs disagree for any submission between 150 and 199 words.
    """
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()  # leader admitted >= 200

    slack = program_with("1", word_count_clause("ge", 150))
    # Sanity: the slack program really does satisfy the public acceptance gate,
    # so the vector layer alone would have let it through.
    fresh = json.loads(policy.evaluate(json.dumps(dict(GOOD, word_count=175))))
    assert fresh["verdict"] == "FAIL"  # under >= 200

    direct_vm.clear_mocks()
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(slack))
    assert direct_vm.run_validator() is False


def test_validator_rejects_an_over_permissive_program(direct_vm, policy):
    """Caught by the acceptance-vector layer inside the validator, before the
    differential comparison is even reached."""
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()

    wide_open = json.dumps(program_with("1", word_count_clause("ge", 0)))
    assert direct_vm.run_validator(leader_result=wide_open) is False


def test_validator_rejects_a_program_that_moves_a_clause_to_residual(direct_vm, policy):
    """Declaring a mechanisable clause residual is a dodge, not a compilation.
    The two sides must agree on what the rule makes checkable."""
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()

    dodged = program_with("3", clause("3", kind="residual", question="Did they include tests?"))
    direct_vm.clear_mocks()
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(dodged))
    assert direct_vm.run_validator() is False


def test_validator_rejects_a_structurally_invalid_leader_result(direct_vm, policy):
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()

    bogus = json.dumps(
        program_with("1", clause("1", effect="require", predicate={"op": "cmp", "field": "ghost", "rel": "eq", "value": 1}))
    )
    assert direct_vm.run_validator(leader_result=bogus) is False
    assert direct_vm.run_validator(leader_result="not even json") is False


def test_validator_disagrees_when_the_leader_errored_but_it_did_not(direct_vm, policy):
    """A leader that produced garbage must not be agreed with; disagreement is
    what rotates consensus to a different leader."""
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()
    assert direct_vm.run_validator(leader_error=RuntimeError("[LLM_ERROR] bad output")) is False

# ------------------------------------------- deterministic gates reject outright
@pytest.mark.parametrize(
    "name,program",
    [
        ("undeclared field", program_with("1", clause("1", effect="require", predicate={"op": "cmp", "field": "nope", "rel": "eq", "value": 1}))),
        ("op not whitelisted", program_with("1", clause("1", effect="require", predicate={"op": "regex", "field": "body", "value": ".*"}))),
        ("wrong literal type", program_with("1", clause("1", effect="require", predicate={"op": "cmp", "field": "word_count", "rel": "ge", "value": "200"}))),
        ("ordering on a str field", program_with("2", clause("2", effect="require", predicate={"op": "cmp", "field": "language", "rel": "gt", "value": "English"}))),
        ("bool literal in an int field", program_with("1", clause("1", effect="require", predicate={"op": "cmp", "field": "word_count", "rel": "ge", "value": True}))),
        ("bad effect", program_with("1", clause("1", effect="maybe", predicate={"op": "cmp", "field": "word_count", "rel": "ge", "value": 200}))),
        ("residual without a question", program_with("4", clause("4", kind="residual", question="   "))),
    ],
)
def test_structural_violations_are_rejected(direct_vm, policy, name, program):
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(program))
    with direct_vm.expect_revert():
        policy.compile_policy()
    assert json.loads(policy.status())["compiled"] is False


def test_missing_or_invented_clauses_are_rejected(direct_vm, policy):
    dropped = {"clauses": [c for c in FAITHFUL["clauses"] if c["id"] != "4"]}
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(dropped))
    with direct_vm.expect_revert():
        policy.compile_policy()

    direct_vm.clear_mocks()
    invented = json.loads(json.dumps(FAITHFUL))
    invented["clauses"].append(clause("9", kind="residual", question="Invented clause?"))
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(invented))
    with direct_vm.expect_revert():
        policy.compile_policy()


def test_an_all_residual_program_is_not_a_compilation(direct_vm, policy):
    dodge = {"clauses": [clause(str(i), kind="residual", question="Judge clause %d?" % i) for i in range(1, 5)]}
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(dodge))
    with direct_vm.expect_revert():
        policy.compile_policy()


def test_acceptance_vectors_reject_a_program_that_passes_a_fail_case(direct_vm, policy):
    """The FAIL vector must fail MECHANICALLY. Routing it to a residual
    judgement instead is exactly the dodge this gate exists to stop."""
    lenient = program_with("1", word_count_clause("ge", 5))
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(lenient))
    with direct_vm.expect_revert():
        policy.compile_policy()

# ----------------------------------------------------------------- versioning
def test_readmitting_the_same_program_is_refused(direct_vm, policy):
    """No no-op version bumps: a version counter that anyone can advance is a
    way to invalidate outstanding adjudications."""
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()
    with direct_vm.expect_revert("identical program"):
        policy.compile_policy()
    assert json.loads(policy.status())["policy_version"] == 1


def test_a_genuinely_different_mechanisation_bumps_the_version(direct_vm, policy):
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()
    first = json.loads(policy.status())

    tighter = program_with("1", word_count_clause("ge", 250))
    direct_vm.clear_mocks()
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(tighter))
    policy.compile_policy()

    second = json.loads(policy.status())
    assert second["policy_version"] == 2
    assert second["policy_digest"] != first["policy_digest"]
    # And the new mechanisation is what enforcement now uses.
    assert json.loads(policy.evaluate(json.dumps(dict(GOOD, word_count=210))))["verdict"] == "FAIL"
