"""Shared fixtures and the running example rule used by the direct-mode tests.

The rule is small on purpose: four clauses, one of which is genuinely not
mechanisable, so every verdict the primitive can produce is reachable.
"""

import json

import pytest

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

GOOD = {"word_count": 500, "language": "English", "has_tests": True, "body": "a thorough writeup"}
TOO_SHORT = {"word_count": 10, "language": "English", "has_tests": True, "body": "brief"}
WRONG_LANG = {"word_count": 500, "language": "French", "has_tests": True, "body": "bon travail"}
NO_TESTS = {"word_count": 500, "language": "English", "has_tests": False, "body": "no tests here"}

VECTORS = [
    {"payload": GOOD, "expect": "PASS"},
    {"payload": TOO_SHORT, "expect": "FAIL"},
    {"payload": WRONG_LANG, "expect": "FAIL"},
]

# A faithful mechanisation of the rule above: three predicates and one honest
# residual declaration.
FAITHFUL = {
    "clauses": [
        {
            "id": "1",
            "kind": "mechanised",
            "effect": "require",
            "predicate": {"op": "cmp", "field": "word_count", "rel": "ge", "value": 200},
        },
        {
            "id": "2",
            "kind": "mechanised",
            "effect": "require",
            "predicate": {"op": "cmp", "field": "language", "rel": "eq", "value": "English"},
        },
        {
            "id": "3",
            "kind": "mechanised",
            "effect": "require",
            "predicate": {"op": "cmp", "field": "has_tests", "rel": "eq", "value": True},
        },
        {"id": "4", "kind": "residual"},
    ]
}


@pytest.fixture
def rule_args():
    return [TITLE, json.dumps(CLAUSES), json.dumps(SCHEMA), json.dumps(VECTORS)]


@pytest.fixture
def policy(deploy, rule_args):
    return deploy("compiled_policy.py", *rule_args)


@pytest.fixture
def compiled(direct_vm, policy):
    """A policy with FAITHFUL admitted, via a mocked compilation."""
    direct_vm.mock_llm(r"compiling a rule", json.dumps(FAITHFUL))
    policy.compile_policy()
    return policy
