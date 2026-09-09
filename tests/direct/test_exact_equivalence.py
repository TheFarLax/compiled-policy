"""The exact equivalence proof, exercised through the real validator.

`tests/proof/` establishes that the abstraction is complete. This file
establishes that the deployed contract actually uses it: `run_validator()`
replays the captured validator closure, so a rejection here is the rejection a
real validator would make.

The specimens are the ones from `tests/proof/test_reviewer_objection.py`, where
they are shown to have slipped past the deleted probe-based check.
"""

import json
from pathlib import Path

import pytest

from conftest import FAITHFUL, GOOD

COMPILE_PROMPT = r"compiling a rule"
CONTRACT_SOURCE = Path(__file__).resolve().parents[2] / "contracts" / "compiled_policy.py"


def swap_clause_one(predicate, effect="require"):
    """FAITHFUL with clause 1's predicate replaced."""
    out = json.loads(json.dumps(FAITHFUL))
    out["clauses"][0] = {"id": "1", "kind": "mechanised", "effect": effect, "predicate": predicate}
    return out


AT_LEAST_200 = {"op": "cmp", "field": "word_count", "rel": "ge", "value": 200}

HOLED_AT_300 = {
    "op": "and",
    "args": [
        AT_LEAST_200,
        {"op": "not", "args": [{"op": "cmp", "field": "word_count", "rel": "eq", "value": 300}]},
    ],
}

WIDENED_UNDER_A_FAILING_CLAUSE = {
    "op": "or",
    "args": [AT_LEAST_200, {"op": "cmp", "field": "has_tests", "rel": "eq", "value": False}],
}


# ====================================================== the reviewer's objection
def test_validator_rejects_a_program_the_old_probe_set_would_have_admitted(direct_vm, policy):
    """THE test for this redesign.

    `>= 200` and `>= 200 except exactly 300` agree on every payload the deleted
    probe generator ever built -- proved in
    tests/proof/test_reviewer_objection.py -- and disagree at 300 words. The
    exhaustive comparison catches it because 300 is a cell of the integer
    partition, not because anything guessed to try it."""
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()  # leader admitted >= 200

    # The specimen is not caught by an earlier layer: it satisfies the vectors.
    assert json.loads(policy.evaluate(json.dumps(dict(GOOD, word_count=300))))["verdict"] == "RESIDUAL_REQUIRED"

    direct_vm.clear_mocks()
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(swap_clause_one(HOLED_AT_300)))
    assert direct_vm.run_validator() is False


def test_validator_rejects_a_difference_no_verdict_vector_could_ever_see(direct_vm, policy):
    """Clause 1 widened only where clause 3 already fails. The whole-program
    verdict is identical for EVERY payload, so comparing verdicts -- with any
    number of probes -- would admit this forever. The proof is per clause."""
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()

    direct_vm.clear_mocks()
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(swap_clause_one(WIDENED_UNDER_A_FAILING_CLAUSE)))
    assert direct_vm.run_validator() is False


def test_validator_still_accepts_genuinely_equivalent_rewrites(direct_vm, policy):
    """Exactness cuts both ways: the proof must not reject a program that is
    merely written differently, or no independent compilation would ever agree."""
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(FAITHFUL))
    policy.compile_policy()

    de_morgan = {
        "op": "not",
        "args": [{"op": "or", "args": [
            {"op": "cmp", "field": "word_count", "rel": "lt", "value": 200},
            {"op": "cmp", "field": "word_count", "rel": "eq", "value": 150},
        ]}],
    }
    direct_vm.clear_mocks()
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(swap_clause_one(de_morgan)))
    assert direct_vm.run_validator() is True


# ============================================================ no sampling left
def test_no_probe_fallback_exists_in_the_contract(direct_vm, policy):
    """A structural guard, because the security claim is about what the code
    CANNOT do. If any of these ever reappear, the contract has a sampling path
    again and this test is the one that should fail first."""
    source = CONTRACT_SOURCE.read_text(encoding="utf-8")
    for symbol in (
        "_MAX_PROBES",
        "_collect_candidates",
        "_base_payload",
        "_probe_payloads",
        "_verdict_vector",
    ):
        assert symbol not in source, "probe-based comparison is back: %s" % symbol
    # And the replacement is the only thing gating admission.
    assert "_prove_equivalent" in source


def test_contract_sources_are_pure_ascii(direct_vm, policy):
    """Not style -- deployability.

    `gltest` fetches a contract's schema by hex-encoding the source with an
    ASCII codec, so one non-ASCII character anywhere in the file, comments
    included, makes every integration test fail at deploy with a
    `UnicodeEncodeError` buried behind "Failed to get schema from all clients".
    A comment about Unicode case folding caused exactly that."""
    for path in sorted((CONTRACT_SOURCE.parent).glob("*.py")):
        text = path.read_text(encoding="utf-8")
        offenders = [(i, ch) for i, ch in enumerate(text) if ord(ch) > 127]
        assert not offenders, "%s: non-ASCII %r at offset %d" % (
            path.name,
            offenders[0][1],
            offenders[0][0],
        )


def test_the_len_operator_is_gone_from_the_grammar(direct_vm, policy):
    """`len` read the raw string while every other string operator reads the
    normalised one, so its equivalence classes could not be enumerated with a
    proof. A program using it is refused outright."""
    source = CONTRACT_SOURCE.read_text(encoding="utf-8")
    ops_line = [ln for ln in source.splitlines() if ln.startswith("_OPS = ")]
    assert ops_line and "len" not in ops_line[0]

    with_len = swap_clause_one({"op": "len", "field": "body", "rel": "ge", "value": 1})
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(with_len))
    with direct_vm.expect_revert():
        policy.compile_policy()
    assert json.loads(policy.status())["compiled"] is False


def test_a_blank_contains_literal_is_refused(direct_vm, policy):
    """An all-whitespace literal normalises to "", a substring of everything --
    a constant-true node, which the grammar does not have and the containment
    enumeration could not represent."""
    blank = swap_clause_one({"op": "contains", "field": "body", "value": "   "})
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(blank))
    with direct_vm.expect_revert():
        policy.compile_policy()
    assert json.loads(policy.status())["compiled"] is False


def test_an_unprovable_program_is_refused_before_it_reaches_a_validator(direct_vm, policy):
    """Exact proof or refusal. A program whose verification space does not fit
    the budget is rejected by the leader with a deterministic error, rather than
    admitted on partial evidence or left for the validators to fail on."""
    huge = swap_clause_one(
        {
            "op": "and",
            "args": [
                {"op": "in", "field": "word_count", "values": list(range(200, 224, 2))},
                {"op": "in", "field": "language", "values": ["l%d" % i for i in range(12)]},
                {"op": "in", "field": "body", "values": ["b%d" % i for i in range(12)]},
            ],
        }
    )
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(huge))
    with direct_vm.expect_revert():
        policy.compile_policy()
    assert json.loads(policy.status())["compiled"] is False


# ================================================ contains survives the redesign
def test_contains_is_still_usable_and_still_proved_exactly(direct_vm, policy):
    """`contains` was kept because its classes ARE enumerable. This drives it
    through a real compilation and a real validator agreement."""
    # "thorough" appears in GOOD's body, so this still satisfies every vector.
    with_contains = swap_clause_one(
        {"op": "and", "args": [AT_LEAST_200, {"op": "contains", "field": "body", "value": "thorough"}]}
    )
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(with_contains))
    policy.compile_policy()

    matching = dict(GOOD, body="a THOROUGH   writeup")  # case and spacing normalised away
    assert json.loads(policy.evaluate(json.dumps(matching)))["verdict"] == "RESIDUAL_REQUIRED"
    assert json.loads(policy.evaluate(json.dumps(dict(GOOD, body="nothing here"))))["verdict"] == "FAIL"

    # An equivalent rewrite agrees, including across `_norm`...
    direct_vm.clear_mocks()
    rewritten = swap_clause_one(
        {"op": "not", "args": [{"op": "or", "args": [
            {"op": "cmp", "field": "word_count", "rel": "lt", "value": 200},
            {"op": "not", "args": [{"op": "contains", "field": "body", "value": "  THOROUGH  "}]},
        ]}]}
    )
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(rewritten))
    assert direct_vm.run_validator() is True

    # ...and a pattern that is merely a near-miss does not.
    direct_vm.clear_mocks()
    other = swap_clause_one(
        {"op": "and", "args": [AT_LEAST_200, {"op": "contains", "field": "body", "value": "thoroughly"}]}
    )
    direct_vm.mock_llm(COMPILE_PROMPT, json.dumps(other))
    assert direct_vm.run_validator() is False
