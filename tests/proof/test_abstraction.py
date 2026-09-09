"""The completeness of the exact abstraction, checked by enumeration.

`_prove_equivalent` claims something strong: that agreement on a finite set of
abstract states is agreement on EVERY payload the schema admits. That claim is
what the second Portal rejection was about, so it is tested by brute force
against the contract's own evaluator rather than argued in a comment.

The property that must never fail is one-sided. A FALSE ACCEPT -- the prover
certifying two clauses as equivalent when some concrete payload separates them
-- is exactly the vulnerability. A false reject would merely be over-strict.
Both are asserted here; only the first is a security claim.
"""

import itertools
import json
import random

import pytest

from harness import UserError, cp

FIELDS = {"n": "int", "s": "str", "b": "bool"}


def atom(**kw):
    return kw


def clause(predicate, effect="require", cid="1"):
    return {"id": cid, "kind": "mechanised", "effect": effect, "predicate": predicate}


def program(*clauses):
    return {"clauses": list(clauses)}


def proves_equivalent(pred_a, pred_b, effect_a="require", effect_b="require"):
    return cp._prove_equivalent(
        program(clause(pred_a, effect_a)), program(clause(pred_b, effect_b)), FIELDS
    )


# ============================================================ per-field classes
def test_int_cells_are_the_exact_partition_of_the_integers():
    """Below the minimum, each constant, each non-empty gap, above the maximum.
    A gap of one has no interior, so no representative is invented for it."""
    assert cp._int_cells([atom(op="cmp", value=200)]) == [199, 200, 201]
    assert cp._int_cells([atom(op="cmp", value=150), atom(op="cmp", value=200)]) == [
        149, 150, 151, 200, 201,
    ]
    # 200 and 201 are adjacent: there is nothing strictly between them.
    assert cp._int_cells([atom(op="cmp", value=200), atom(op="cmp", value=201)]) == [
        199, 200, 201, 202,
    ]
    assert cp._int_cells([atom(op="in", values=[1, 5])]) == [0, 1, 2, 5, 6]


def test_every_int_atom_is_constant_inside_its_cell():
    """The invariance the int abstraction rests on, checked exhaustively over a
    concrete range: two integers in the same cell cannot be separated by any
    atom built from the constants that defined the cells."""
    constants = [-3, 0, 7, 8, 40]
    atoms = [atom(op="cmp", field="n", rel=rel, value=k) for k in constants for rel in cp._RELS_ORD]
    atoms.append(atom(op="in", field="n", values=constants))
    cells = cp._int_cells(atoms)

    def cell_of(x):
        # The cell a concrete integer belongs to, by the same definition.
        for index, value in enumerate(sorted(constants)):
            if x < value:
                return index * 2
            if x == value:
                return index * 2 + 1
        return len(constants) * 2

    by_cell = {}
    for x in range(-60, 90):
        by_cell.setdefault(cell_of(x), []).append(x)

    # Every cell that contains an integer in range has a representative, and
    # every atom agrees across the whole cell.
    represented = {cell_of(r) for r in cells}
    for key, members in by_cell.items():
        assert key in represented, "cell %d has no representative" % key
        for node in atoms:
            values = {cp._eval_node(node, {"n": x, "s": "", "b": False}) for x in members}
            assert len(values) == 1, (node, key, members[:5])


def test_bool_classes_are_the_whole_domain():
    assert cp._field_classes("bool", []) == [True, False]


def test_string_equality_classes_are_one_per_literal_plus_other():
    reps = cp._str_classes([atom(op="cmp", value="English"), atom(op="in", values=["French"])])
    normalised = [cp._norm(r) for r in reps]
    assert "english" in normalised and "french" in normalised
    # Exactly one extra class: "equal to neither".
    assert len(reps) == 3
    assert len([r for r in reps if cp._norm(r) not in ("english", "french")]) == 1


def test_literals_are_deduplicated_by_their_normalised_form():
    """`_norm` lowercases and collapses whitespace, so these three literals name
    ONE class, not three. Counting them separately would inflate the state space
    without adding coverage."""
    reps = cp._str_classes(
        [
            atom(op="cmp", value="English"),
            atom(op="cmp", value="  ENGLISH  "),
            atom(op="in", values=["english", "eNgLiSh"]),
        ]
    )
    assert len(reps) == 2  # the one literal class, plus "equal to neither"
    assert len({cp._norm(r) for r in reps}) == 2


def test_realisable_contains_classes_are_enumerated():
    """Two independent patterns give four containment sets, all realisable, and
    each witness really does realise its own."""
    reps = cp._str_classes([atom(op="contains", value="ab"), atom(op="contains", value="cd")])
    vectors = {(("ab" in cp._norm(r)), ("cd" in cp._norm(r))) for r in reps}
    assert vectors == {(False, False), (True, False), (False, True), (True, True)}


def test_impossible_contains_combinations_are_not_invented():
    """"abc" cannot appear without "ab" appearing too, so the containment set
    {abc} is unrealisable and must not become an abstract state. Three classes,
    not four -- and no witness claims the impossible one."""
    reps = cp._str_classes([atom(op="contains", value="ab"), atom(op="contains", value="abc")])
    vectors = {(("ab" in cp._norm(r)), ("abc" in cp._norm(r))) for r in reps}
    assert vectors == {(False, False), (True, False), (True, True)}
    assert (False, True) not in vectors
    assert len(reps) == 3


def test_a_contains_witness_never_smuggles_in_an_unwanted_pattern():
    """Witnesses are joined with a separator absent from every pattern, so no
    pattern can straddle a join. Checked on patterns chosen to overlap."""
    patterns = ["ab", "ba", "aba"]
    reps = cp._str_classes([atom(op="contains", value=p) for p in patterns])
    seen = set()
    for rep in reps:
        normalised = cp._norm(rep)
        seen.add(tuple(p in normalised for p in patterns))
    # Every enumerated class is distinct and downward closed under substring.
    assert len(seen) == len(reps)
    for vector in seen:
        if vector[2]:  # contains "aba" => contains both "ab" and "ba"
            assert vector[0] and vector[1]


def test_too_many_contains_patterns_on_one_field_is_refused_not_approximated():
    atoms = [atom(op="contains", value="p%d" % i) for i in range(cp._MAX_CONTAINS_PER_FIELD + 1)]
    with pytest.raises(UserError) as excinfo:
        cp._str_classes(atoms)
    assert "contains patterns" in excinfo.value.message


# ============================================================== the proof itself
def test_the_state_space_covers_every_field_both_clauses_mention():
    a = clause({"op": "cmp", "field": "n", "rel": "ge", "value": 5})
    b = clause({"op": "cmp", "field": "b", "rel": "eq", "value": True})
    states = cp._abstract_states(a, b, FIELDS)
    assert {s["n"] for s in states} == {4, 5, 6}
    assert {s["b"] for s in states} == {True, False}
    assert len(states) == 6
    # A field neither clause reads is pinned: varying it could change nothing.
    assert {s["s"] for s in states} == {""}


WIDE_FIELDS = {"n": "int", "s": "str", "t": "str", "u": "str", "b": "bool"}

# 12 integer constants -> 25 cells; 12 string literals -> 13 classes.
_MANY_INTS = list(range(0, 24, 2))
_MANY_STRS = ["p%d" % i for i in range(12)]


def test_exceeding_the_per_clause_state_cap_refuses_rather_than_sampling():
    """The invariant: exact proof or refusal. There is no third outcome where a
    program is admitted on partial evidence. 25 x 13 x 13 = 4225 states."""
    wide = clause(
        {
            "op": "and",
            "args": [
                {"op": "in", "field": "n", "values": _MANY_INTS},
                {"op": "in", "field": "s", "values": _MANY_STRS},
                {"op": "in", "field": "t", "values": _MANY_STRS},
            ],
        }
    )
    with pytest.raises(UserError) as excinfo:
        cp._abstract_states(wide, wide, WIDE_FIELDS)
    assert "more than %d states for one clause" % cp._MAX_STATES_PER_CLAUSE in excinfo.value.message


def test_the_total_budget_is_enforced_across_clauses():
    """Each clause fits on its own (325 states); 64 of them do not."""
    heavy = clause(
        {
            "op": "and",
            "args": [
                {"op": "in", "field": "n", "values": _MANY_INTS},
                {"op": "in", "field": "s", "values": _MANY_STRS},
            ],
        }
    )
    assert len(cp._abstract_states(heavy, heavy, WIDE_FIELDS)) < cp._MAX_STATES_PER_CLAUSE

    clauses = []
    for index in range(64):
        entry = json.loads(json.dumps(heavy))
        entry["id"] = str(index)
        clauses.append(entry)
    with pytest.raises(UserError) as excinfo:
        cp._prove_equivalent(program(*clauses), program(*clauses), WIDE_FIELDS)
    assert "more than %d states" % cp._MAX_STATES_TOTAL in excinfo.value.message


def test_check_provable_refuses_a_program_no_validator_could_ever_prove():
    """A program can be structurally legal, satisfy every acceptance vector, and
    still be unprovable. The leader refuses it up front instead of leaving the
    validators to disagree about it."""
    wide = clause(
        {
            "op": "and",
            "args": [
                {"op": "in", "field": "n", "values": _MANY_INTS},
                {"op": "in", "field": "s", "values": _MANY_STRS},
                {"op": "in", "field": "t", "values": _MANY_STRS},
            ],
        }
    )
    with pytest.raises(UserError):
        cp._check_provable(program(wide), WIDE_FIELDS)
    # And a modest one is accepted without complaint.
    cp._check_provable(program(clause({"op": "cmp", "field": "n", "rel": "ge", "value": 5})), WIDE_FIELDS)


def test_equivalent_programs_written_differently_are_proved_equal():
    ge = {"op": "cmp", "field": "n", "rel": "ge", "value": 5}
    not_lt = {"op": "not", "args": [{"op": "cmp", "field": "n", "rel": "lt", "value": 5}]}
    assert proves_equivalent(ge, not_lt) is True
    # De Morgan, across two fields.
    left = {"op": "not", "args": [{"op": "and", "args": [ge, {"op": "cmp", "field": "b", "rel": "eq", "value": True}]}]}
    right = {
        "op": "or",
        "args": [
            {"op": "cmp", "field": "n", "rel": "lt", "value": 5},
            {"op": "cmp", "field": "b", "rel": "eq", "value": False},
        ],
    }
    assert proves_equivalent(left, right) is True
    # `require p` == `forbid not p`.
    assert proves_equivalent(ge, {"op": "not", "args": [ge]}, "require", "forbid") is True


def test_a_single_integer_of_difference_is_caught():
    """The whole point. These two agree on every integer except 300, and 300 is
    not adjacent to any literal either program mentions."""
    ge = {"op": "cmp", "field": "n", "rel": "ge", "value": 200}
    holed = {
        "op": "and",
        "args": [ge, {"op": "not", "args": [{"op": "cmp", "field": "n", "rel": "eq", "value": 300}]}],
    }
    assert proves_equivalent(ge, holed) is False


def test_a_single_string_of_difference_is_caught():
    eq = {"op": "cmp", "field": "s", "rel": "eq", "value": "english"}
    widened = {"op": "in", "field": "s", "values": ["english", "british"]}
    assert proves_equivalent(eq, widened) is False


def test_effect_inversion_is_part_of_the_comparison():
    """`require p` and `forbid p` are opposites, and the prover compares clause
    SATISFACTION rather than predicate truth, so it must say so."""
    predicate = {"op": "cmp", "field": "b", "rel": "eq", "value": True}
    assert proves_equivalent(predicate, predicate, "require", "forbid") is False
    assert proves_equivalent(predicate, predicate, "require", "require") is True


def test_clauses_are_matched_by_id_not_by_position():
    """Comparing clause 1 against clause 2 would be a silent hole: two programs
    could each be right about one clause and wrong about the other."""
    p1 = {"op": "cmp", "field": "n", "rel": "ge", "value": 5}
    p2 = {"op": "cmp", "field": "b", "rel": "eq", "value": True}
    left = program(clause(p1, cid="1"), clause(p2, cid="2"))
    swapped = program(clause(p2, cid="1"), clause(p1, cid="2"))
    assert cp._prove_equivalent(left, left, FIELDS) is True
    assert cp._prove_equivalent(left, swapped, FIELDS) is False


def test_a_differing_mechanised_residual_split_is_rejected():
    p = {"op": "cmp", "field": "n", "rel": "ge", "value": 5}
    left = program(clause(p, cid="1"), clause(p, cid="2"))
    dodged = program(clause(p, cid="1"), {"id": "2", "kind": "residual"})
    assert cp._prove_equivalent(left, dodged, FIELDS) is False


# ====================================================== brute force cross-check
INT_CONSTANTS = [0, 1, 2, 5]
STR_LITERALS = ["aa", "bb", " AA ", "ab"]
PATTERNS = ["a", "b", "ab", "ba"]

_ALPHABET = ["a", "b", " ", "A"]
_STRINGS = [""]
for _length in (1, 2, 3, 4):
    for _combo in itertools.product(_ALPHABET, repeat=_length):
        _STRINGS.append("".join(_combo))
_STRINGS += STR_LITERALS + ["aaa bbb", "xyz", "AB", "  ab  "]

CONCRETE = [
    {"n": n, "s": s, "b": b}
    for n in range(-2, 9)
    for s in _STRINGS
    for b in (True, False)
]


def _random_atom(rng):
    kind = rng.choice(["int", "int", "str", "str", "str", "bool"])
    if kind == "int":
        if rng.random() < 0.75:
            return {"op": "cmp", "field": "n", "rel": rng.choice(list(cp._RELS_ORD)),
                    "value": rng.choice(INT_CONSTANTS)}
        return {"op": "in", "field": "n", "values": rng.sample(INT_CONSTANTS, rng.randint(1, 3))}
    if kind == "bool":
        return {"op": "cmp", "field": "b", "rel": rng.choice(list(cp._RELS_EQ)),
                "value": rng.choice([True, False])}
    roll = rng.random()
    if roll < 0.4:
        return {"op": "contains", "field": "s", "value": rng.choice(PATTERNS)}
    if roll < 0.7:
        return {"op": "cmp", "field": "s", "rel": rng.choice(list(cp._RELS_EQ)),
                "value": rng.choice(STR_LITERALS)}
    return {"op": "in", "field": "s", "values": rng.sample(STR_LITERALS, rng.randint(1, 2))}


def _random_node(rng, depth=0):
    if depth >= 2 or rng.random() < 0.45:
        return _random_atom(rng)
    op = rng.choice(["and", "or", "not"])
    if op == "not":
        return {"op": "not", "args": [_random_node(rng, depth + 1)]}
    return {"op": op, "args": [_random_node(rng, depth + 1) for _ in range(rng.randint(2, 3))]}


def _random_clause(rng):
    return clause(_random_node(rng), rng.choice(["require", "forbid"]))


def _concrete_counterexample(left, right):
    for payload in CONCRETE:
        if cp._clause_satisfied(left, payload) != cp._clause_satisfied(right, payload):
            return payload
    return None


@pytest.mark.parametrize("seed", [20260908, 11, 22])
def test_the_proof_matches_brute_force_over_a_concrete_payload_space(seed):
    """The completeness claim, tested rather than asserted.

    Random clause pairs, each decided two ways: by the prover over its abstract
    states, and by enumerating a large concrete payload space with the
    contract's own `_clause_satisfied`. The two verdicts must agree every time.

    Deliberately biased towards near-misses -- half the pairs are a mutation of
    the other -- because a prover that only distinguishes obviously different
    programs would pass an unbiased sample easily.
    """
    rng = random.Random(seed)
    equivalent = 0
    different = 0
    for _round in range(220):
        left = _random_clause(rng)
        if rng.random() < 0.5:
            right = _random_clause(rng)
        else:
            right = json.loads(json.dumps(left))
            if rng.random() < 0.5:
                right["effect"] = "require" if right["effect"] == "forbid" else "forbid"
                right["predicate"] = {"op": "not", "args": [right["predicate"]]}
            else:
                right["predicate"] = {"op": rng.choice(["and", "or"]),
                                      "args": [right["predicate"], _random_atom(rng)]}

        proved = cp._prove_equivalent(program(left), program(right), FIELDS)
        witness = _concrete_counterexample(left, right)

        assert not (proved and witness is not None), (
            "FALSE ACCEPT -- proved equivalent but %r separates them:\n  A=%r\n  B=%r"
            % (witness, left, right)
        )
        assert not (witness is None and not proved), (
            "false reject -- no concrete payload separates these:\n  A=%r\n  B=%r" % (left, right)
        )
        if proved:
            equivalent += 1
        else:
            different += 1

    # Guard against the test silently degenerating into "everything differs".
    assert equivalent >= 20 and different >= 20, (equivalent, different)
