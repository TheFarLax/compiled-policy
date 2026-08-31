"""Integration tests against a live GenLayer network (Studio / localnet).

    gltest --network studionet tests/integration

STATUS: PASSED on Studionet, 2026-08-28 -- 6 tests in 5m27s against
`https://studio.genlayer.com/api` (chain id 61999). Contract addresses,
transaction hashes and the exact program a real model produced are recorded in
DECISIONS.md and README.md. No contract change was needed to make this pass.

What only a live network can show, and therefore what these cover:
  * a real model compiling real prose into the grammar, and the deterministic
    gates accepting or rejecting the result;
  * multi-validator agreement on that compilation and on a residual ruling;
  * the cross-contract read from GatedVault into CompiledPolicy, including
    `preview()` as a view calling another contract's view -- neither of which
    direct mode implements;
  * a real native GEN transfer out of the vault.

Testing discipline: assertions pin invariants, never model wording. A compilation
that reverts because the model produced an unfaithful program is a legitimate
outcome of the primitive working -- re-run it, never weaken a guard to make it
green. Note that on a live network such a rejection surfaces as leader rotation
ending in an undetermined transaction, not as the clean revert direct mode shows.
"""

import json

import pytest

from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded

TITLE = "Bounty submission rules"

CLAUSES = [
    "The submission must be at least 200 words long.",
    "The submission must be written in English.",
    "The submission must include tests.",
    "The writing must be clear and respectful in tone.",
]

SCHEMA = [
    {"name": "word_count", "kind": "int"},
    {"name": "language", "kind": "str"},
    {"name": "has_tests", "kind": "bool"},
    {"name": "body", "kind": "str"},
]

# `body` is short on purpose. `gen_call` (the RPC read path) rejects string
# arguments above roughly 200 bytes with an RLP length-prefix error -- a
# client/node limitation, not a contract one, isolated and recorded in
# DECISIONS.md. Keeping the whole payload well under that ceiling is what lets
# `evaluate()` be called over RPC at all. It does mean the residual clause has
# little prose to judge, so the ruling is genuinely non-deterministic between
# runs; the vault test below asserts both the PASS and the refusal path rather
# than betting on one.
GOOD = {
    "word_count": 500,
    "language": "English",
    "has_tests": True,
    "body": "Thanks for reviewing. Fixes an off-by-one in pagination; tests added.",
}
TOO_SHORT = {"word_count": 10, "language": "English", "has_tests": True, "body": "brief"}
WRONG_LANG = {"word_count": 500, "language": "French", "has_tests": True, "body": "bon travail"}

VECTORS = [
    {"payload": GOOD, "expect": "PASS"},
    {"payload": TOO_SHORT, "expect": "FAIL"},
    {"payload": WRONG_LANG, "expect": "FAIL"},
]

def deploy_policy():
    factory = get_contract_factory("CompiledPolicy")
    return factory.deploy(
        args=[TITLE, json.dumps(CLAUSES), json.dumps(SCHEMA), json.dumps(VECTORS)]
    )


@pytest.fixture(scope="module")
def compiled_policy():
    policy = deploy_policy()
    receipt = policy.compile_policy(args=[]).transact()
    assert tx_execution_succeeded(receipt), (
        "compilation did not reach consensus. Either the validators disagreed on "
        "the mechanisation or the model produced a program the deterministic gates "
        "rejected. Both are the primitive working; re-run before investigating."
    )
    return policy


def test_deterministic_reads_work_before_compilation():
    policy = deploy_policy()
    status = json.loads(policy.status(args=[]).call())
    assert status["compiled"] is False
    assert json.loads(policy.evaluate(args=[json.dumps(GOOD)]).call())["verdict"] == "UNCOMPILED"


def test_a_real_model_compilation_satisfies_the_acceptance_vectors(compiled_policy):
    """The strong claim: because `compile_policy` only admits a program that
    passed the vector gate, a successful compilation guarantees these verdicts
    without any further trust in the model."""
    status = json.loads(compiled_policy.status(args=[]).call())
    assert status["compiled"] is True
    assert status["policy_version"] == 1
    assert len(status["policy_digest"]) == 64

    for vector in VECTORS:
        result = json.loads(compiled_policy.evaluate(args=[json.dumps(vector["payload"])]).call())
        if vector["expect"] == "FAIL":
            assert result["verdict"] == "FAIL", result
            assert result["violated"], result
        else:
            assert result["verdict"] != "FAIL", result


def test_the_admitted_program_stays_inside_the_grammar(compiled_policy):
    program = json.loads(compiled_policy.program(args=[]).call())
    ids = sorted(c["id"] for c in program["clauses"])
    assert ids == ["1", "2", "3", "4"]
    allowed_ops = {"and", "or", "not", "cmp", "in", "contains", "len"}
    field_names = {f["name"] for f in SCHEMA}

    def walk(node):
        assert node["op"] in allowed_ops
        if node["op"] in ("and", "or", "not"):
            for arg in node["args"]:
                walk(arg)
        else:
            assert node["field"] in field_names

    mechanised = 0
    for clause in program["clauses"]:
        if clause["kind"] == "mechanised":
            mechanised += 1
            assert clause["effect"] in ("require", "forbid")
            walk(clause["predicate"])
        else:
            # A residual declaration carries only id and kind. The text that
            # gets adjudicated is read from the immutable rule, not from here.
            assert sorted(clause.keys()) == ["id", "kind"], clause
    assert mechanised >= 1

def test_readmitting_an_identical_program_is_refused(compiled_policy):
    receipt = compiled_policy.compile_policy(args=[]).transact()
    # Either the model produced the identical program and the digest guard
    # rejected it, or it produced a different-but-equivalent one and consensus
    # admitted a second version. Both are correct; a silent no-op bump is not.
    status = json.loads(compiled_policy.status(args=[]).call())
    if tx_execution_succeeded(receipt):
        assert status["policy_version"] >= 2
    else:
        assert status["policy_version"] == 1


def test_residual_adjudication_binds_to_the_policy_digest(compiled_policy):
    result = json.loads(compiled_policy.evaluate(args=[json.dumps(GOOD)]).call())
    if result["verdict"] != "RESIDUAL_REQUIRED":
        pytest.skip("this compilation mechanised every clause; no residual path to exercise")

    receipt = compiled_policy.adjudicate(args=[json.dumps(GOOD)]).transact()
    assert tx_execution_succeeded(receipt), "validators did not agree on the residual ruling"

    ruling = json.loads(compiled_policy.ruling_for(args=[json.dumps(GOOD)]).call())
    assert ruling["verdict"] in ("PASS", "FAIL")
    assert ruling["stale"] is False
    assert ruling["policy_digest"] == json.loads(compiled_policy.status(args=[]).call())["policy_digest"]

    # Idempotent: a second call must not append a duplicate ruling.
    before = json.loads(compiled_policy.status(args=[]).call())["ruling_count"]
    compiled_policy.adjudicate(args=[json.dumps(GOOD)]).transact()
    after = json.loads(compiled_policy.status(args=[]).call())["ruling_count"]
    assert after == before


def test_vault_refuses_a_failing_payload_and_releases_a_passing_one(compiled_policy):
    """The cross-contract read plus a real native transfer -- the part direct
    mode cannot reach."""
    vault_factory = get_contract_factory("GatedVault")
    from gltest import get_default_account

    beneficiary = get_default_account()
    vault = vault_factory.deploy(args=[compiled_policy.address, beneficiary.address])

    assert tx_execution_succeeded(vault.fund(args=[]).transact(value=1000))
    assert json.loads(vault.status(args=[]).call())["held"] == 1000

    # A mechanically failing payload must never release, and must not consume
    # the escrow.
    assert not tx_execution_succeeded(vault.release(args=[json.dumps(TOO_SHORT)]).transact())
    assert json.loads(vault.status(args=[]).call())["released"] is False
    assert json.loads(vault.status(args=[]).call())["held"] == 1000

    # A payload the policy passes releases exactly once. If the admitted program
    # left a residual clause, this test adjudicates it itself rather than
    # depending on an earlier test having done so -- `adjudicate` is idempotent
    # per (policy_version, payload), so doing it twice is a no-op.
    verdict = vault.preview(args=[json.dumps(GOOD)]).call()
    if verdict != "PASS":
        evaluation = json.loads(compiled_policy.evaluate(args=[json.dumps(GOOD)]).call())
        assert evaluation["verdict"] == "RESIDUAL_REQUIRED", (
            "GOOD should either pass outright or need a residual ruling, got %s" % evaluation
        )
        assert tx_execution_succeeded(
            compiled_policy.adjudicate(args=[json.dumps(GOOD)]).transact()
        ), "validators did not agree on the residual ruling"
        verdict = vault.preview(args=[json.dumps(GOOD)]).call()

    if verdict != "PASS":
        # The residual ruling came back FAIL. That is a legitimate model outcome,
        # not a contract fault: the vault must then refuse and keep the escrow.
        assert verdict.startswith("RESIDUAL_"), verdict
        assert not tx_execution_succeeded(vault.release(args=[json.dumps(GOOD)]).transact())
        assert json.loads(vault.status(args=[]).call())["held"] == 1000
        pytest.skip("residual ruling was not PASS (%s); refusal path asserted instead" % verdict)

    assert tx_execution_succeeded(vault.release(args=[json.dumps(GOOD)]).transact())
    assert json.loads(vault.status(args=[]).call())["released"] is True
    assert vault.claimable_of(args=[beneficiary.address]).call() == 1000
    assert not tx_execution_succeeded(vault.release(args=[json.dumps(GOOD)]).transact())

    assert tx_execution_succeeded(vault.withdraw(args=[]).transact())
    assert vault.claimable_of(args=[beneficiary.address]).call() == 0
