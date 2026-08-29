"""GatedVault: the reference-consumer guards that are reachable without a network.

Direct mode implements storage, value and the non-deterministic surfaces, but not
cross-contract calls (`CallContract`) or outbound value (`PostMessage`). So the
parts of GatedVault that read the policy or emit a transfer are covered by
tests/test_integration.py instead, and what remains here are the deterministic
guards that run before any cross-contract read.
"""

import json

import pytest

from conftest import GOOD

ZERO = "0x0000000000000000000000000000000000000000"
POLICY = "0x1111111111111111111111111111111111111111"
BENEFICIARY = "0x2222222222222222222222222222222222222222"


@pytest.fixture
def vault(deploy):
    return deploy("gated_vault.py", POLICY, BENEFICIARY)


def test_constructor_rejects_a_zero_policy(deploy, direct_vm):
    with direct_vm.expect_revert("policy address required"):
        deploy("gated_vault.py", ZERO, BENEFICIARY)


def test_constructor_rejects_a_zero_beneficiary(deploy, direct_vm):
    with direct_vm.expect_revert("beneficiary required"):
        deploy("gated_vault.py", POLICY, ZERO)


def test_deploys_empty_and_unreleased(vault):
    status = json.loads(vault.status())
    assert status["held"] == 0
    assert status["released"] is False
    assert status["last_verdict"] == ""
    assert status["policy"].lower() == POLICY


def test_fund_requires_value_and_accumulates(direct_vm, vault):
    with direct_vm.expect_revert("send some value"):
        vault.fund()

    direct_vm.value = 1000
    vault.fund()
    direct_vm.value = 250
    vault.fund()
    direct_vm.value = 0
    assert json.loads(vault.status())["held"] == 1250


def test_release_refuses_before_anything_is_escrowed(direct_vm, vault):
    """This guard fires before the cross-contract read, so it is reachable here
    and proves the ordering: no policy call is made for an empty vault."""
    with direct_vm.expect_revert("nothing escrowed"):
        vault.release(json.dumps(GOOD))


def test_withdraw_refuses_an_empty_ledger(direct_vm, vault):
    with direct_vm.expect_revert("nothing to withdraw"):
        vault.withdraw()
    assert vault.claimable_of(BENEFICIARY) == 0
