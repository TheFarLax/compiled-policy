# CompiledPolicy

**A GenLayer primitive that spends consensus once — on translating a prose rule
into a machine-checkable program — and is deterministic forever after.**

A rule that matters to people is written in prose. Enforcing one on-chain today
means paying for an LLM judgement on every single evaluation and accepting a
fresh chance of inconsistency each time. The rule is never actually pinned down;
every call re-litigates it.

`CompiledPolicy` inverts that. The validator set is asked one question — *is this
predicate program a faithful mechanisation of this prose?* — and once a program is
admitted, `evaluate()` is a deterministic view. No model. No network. No
consensus. Free, reproducible byte for byte, and callable synchronously from any
other contract's deterministic region.

```
prose clauses ──► [ ONE consensus round ] ──► predicate program (stored, digested)
                                                        │
payload ────────────────────────────────────────────────┼──► deterministic verdict
                                                        │    PASS / FAIL /
                                                        │    RESIDUAL_REQUIRED /
                                                        │    INVALID_PAYLOAD /
                                                        │    UNCOMPILED
                                    residual clauses ───┘
                                          │
                                          └─► [ second consensus round, bound to
                                                the policy digest ]
```

---

## Why this needs GenLayer

The translation from prose to executable logic is a judgement about **meaning**,
and it is the only part of the system that is.

- A normal smart contract cannot make that judgement at all.
- Compiled off-chain, the program is one party's reading of the rule, and every
  consumer has to trust that party. There is no artefact a chain can check.
- On GenLayer, each validator independently compiles the same prose and the two
  programs must agree **behaviourally** — identical verdicts across a probe set
  derived from both programs. That is semantic equivalence of independently
  generated code, decided by execution rather than by opinion.

Everything after admission is ordinary deterministic computation, which is
exactly where it belongs. GenLayer is used for the one step that needs it.

## How consensus works, and how validators check the leader

`compile_policy()` runs a custom leader/validator pair through
`gl.vm.run_nondet_unsafe`. The validator does **not** inspect the leader's output
for a valid shape and an allowed label — that would prove only that the leader
formatted its answer. It re-does the work. Three layers, and only one of them is
a judgement:

**1. Structural — deterministic.**
The program must parse into the whitelisted grammar, reference only declared
fields with type-correct literals, stay inside the node and depth caps, and cover
*exactly* the clause ids fixed at deploy time. Coverage is arithmetic: the
compiler can neither invent a clause nor quietly drop one. At least one clause
must be mechanised, so declaring everything residual is not a compilation.

**2. Behavioural — deterministic.**
The program is executed against the acceptance vectors fixed at deploy time.
Every vector marked `FAIL` must fail **mechanically** — reaching
`RESIDUAL_REQUIRED` is not good enough, because that would let a compiler route
every hard case to a later judgement instead of implementing the clause. This is
the layer that makes an over-permissive program unrepresentable.

**3. Differential — deterministic comparison of two nondeterministic outputs.**
The validator compiles its **own** program from the same prose, requires the same
mechanised/residual split, and then compares verdict vectors over a probe set
built from the literals of *both* programs (each integer literal contributes
`v-1, v, v+1`; string literals contribute themselves and a near-miss; `len`
bounds contribute strings that straddle them). Programs that differ in shape but
not in behaviour agree. Programs that differ anywhere near a literal do not.

Why layer 3 earns its keep: a compilation of *"at least 200 words"* as
`word_count >= 150` satisfies every acceptance vector — the `FAIL` vector has 10
words and still fails, the `PASS` vector has 500 and still passes. Only an
independent compilation compared at the boundary notices that the two programs
disagree for any submission between 150 and 199 words. That case is
`test_validator_rejects_a_threshold_the_acceptance_vectors_cannot_catch`, and it
is the reason this design exists.

The second consensus round, `adjudicate()`, is comparative in the same spirit:
the validator independently re-judges the residual clauses and the per-clause
boolean vector must match exactly. No tolerance — these are booleans about
clauses, so "close enough" is not a meaningful idea.

### Layer 3 requires more than one validator

Layers 1 and 2 are deterministic, so they run on every node and again in the
deterministic region after consensus returns. **Layer 3 cannot be re-checked
after consensus** — it needs a second, independent compilation, which only a
validator can produce.

That has a concrete consequence: on a network configured **leader-only** (a
single validator, or `gltest --leader-only`), the differential layer never runs,
and a program that satisfies the acceptance vectors but is subtly wrong — the
`>= 150` case below — would be admitted. Do not rely on this primitive in a
leader-only configuration. With a real validator set it is the layer that carries
the security argument.

### There is no model-reported confidence anywhere

No `confidence`, no `score`, no `agreement` field is ever stored or gated on. The
model is asked for an `overall` verdict in the residual round and that field is
deliberately **discarded**: the verdict is recomputed on-chain from the
per-clause rulings. A model cannot self-certify an aggregate here.

### Residual clauses are bound to the immutable rule

A residual declaration is `{"id", "kind"}` and nothing else. When `adjudicate()`
runs, the text put in front of the model is read back from `self.clauses` — the
prose fixed by the constructor — addressed by clause id.

This is the whole security argument for the residual path, and it is the one thing
an earlier version of this contract got wrong. Previously the compiler supplied its
own `question` for each residual clause, and that string was stored and later became
the wording adjudicated for `PASS`. Nothing constrained it: the mechanised/residual
split matched, the acceptance vectors were unaffected, and a residual clause cannot
influence a verdict vector, so the differential comparison was structurally blind to
it. A leader could declare *"The writing must be clear and respectful in tone"*
residual with the question *"Is the submission non-empty?"*, pass every gate, and
have every subsequent adjudication rule on a question the rule never asked.

Deriving the text from immutable storage removes that surface rather than policing
it. The residual declaration is now pure id + kind, which is exactly what
`_kind_signature` already compares between the two independent compilations — so
nothing about a residual clause escapes consensus. `_validate_program` **rejects** any
extra field on a residual clause rather than ignoring it, so the substitution is
inexpressible rather than merely unused. Two tests pin the binding in both
directions — the immutable clause prose must reach the adjudicator, and the
substituted wording must not — and both were mutation-tested against the old
behaviour.

## The grammar

Small on purpose. The whitelist **is** the security boundary: nothing in the
prose rule and nothing the model emits can widen it, because these are code
constants.

```
{"op":"and","args":[node,node,...]}          two or more
{"op":"or","args":[node,node,...]}           two or more
{"op":"not","args":[node]}                   exactly one
{"op":"cmp","field":F,"rel":R,"value":L}     int: eq ne lt le gt ge
                                             str/bool: eq ne only
{"op":"in","field":F,"values":[L,...]}       int or str fields
{"op":"contains","field":F,"value":"text"}   str fields
{"op":"len","field":F,"rel":R,"value":N}     str fields, N >= 0
```

There is **no true/false literal**. Every predicate must reference a declared
field, which is what lets the acceptance vectors catch an over-permissive
compilation. Field kinds are `int`, `str`, `bool`; literals must match the kind
exactly (an `int` field rejects `true`, since `bool` subclasses `int` in Python).
Caps: depth 5, 48 nodes, 16 clauses, 8 fields, 12 vectors, 96 probes.

String comparison uses one declared normalisation — lowercase, collapse
whitespace, strip — applied to both sides, so `"  ENGLISH  "` matches `"English"`
and casing cannot be used to dodge a clause.

A program looks like this:

```json
{"clauses": [
  {"id": "1", "kind": "mechanised", "effect": "require",
   "predicate": {"op": "cmp", "field": "word_count", "rel": "ge", "value": 200}},
  {"id": "4", "kind": "residual"}
]}
```

A residual clause carries **only its id**. The text adjudicated later is read back
from the immutable rule, addressed by that id — the compiler never authors it. See
"Residual clauses are bound to the immutable rule" below for why that matters.

`effect: "require"` means the predicate must be **true** to pass;
`effect: "forbid"` means it must be **false**. Both are supported because
`require x >= 200` and `forbid x < 200` are the same rule, and the differential
comparison treats them as equivalent.

## State transitions

```
                    constructor
                        │  rule, schema and acceptance vectors are IMMUTABLE
                        ▼
                   UNCOMPILED ──────────────► evaluate() = UNCOMPILED
                        │
        compile_policy()│ owner only; consensus + 3 gates
                        ▼
   ┌───────────────► ACTIVE v1 ────────────► evaluate() is deterministic
   │                    │
   │   compile_policy() │ a *different* program only
   └──── ACTIVE v2 ◄────┘ identical digest is refused, so no no-op bumps
                        │
                freeze()│ owner only, irreversible
                        ▼
                     FROZEN ───────────────► evaluate() and adjudicate() still work;
                                             only recompilation is closed off
```

The **rule** is immutable; only its **mechanisation** is upgradeable, and every
candidate must pass the same public acceptance vectors. Residual rulings are
recorded against the policy version and digest they were decided under, so a new
mechanisation does not silently inherit old judgements.

## Failure behaviour — nothing accidental ever passes

Five verdicts; exactly one authorises anything.

| Verdict | When | Costs a model call? |
|---|---|---|
| `UNCOMPILED` | no program admitted yet | no |
| `INVALID_PAYLOAD` | payload is not JSON, or does not typecheck against the schema | no |
| `FAIL` | a mechanised clause was violated; the violated ids are returned | no |
| `RESIDUAL_REQUIRED` | mechanised clauses all satisfied, residual clauses remain | no |
| `PASS` | every clause satisfied mechanically | no |

- A mechanical `FAIL` short-circuits: `adjudicate()` refuses to run at all, so a
  violated predicate can never be overridden by a residual ruling, and a failing
  payload never costs an LLM call.
- `RESIDUAL_REQUIRED` is a **refusal**, not a pass. A consumer that treats it as
  a pass has misread the primitive; `GatedVault` shows the correct handling.
- An `INVALID_PAYLOAD` returns a verdict token rather than reverting, so a
  consumer can branch instead of losing the transaction — but it is never `PASS`.
- If validators cannot agree, the transaction is undetermined and **no state
  changes**. An unadmitted program leaves the previous version untouched.
- `adjudicate()` is idempotent per `(policy_version, payload)`. An appeal
  re-executing the transaction returns the recorded ruling instead of appending a
  duplicate or crediting anything twice.

### Rejected compilations: revert in direct mode, rotation on a live network

Worth knowing before you read the tests. Grammar, coverage and acceptance-vector
violations are raised with an `[LLM_ERROR]` prefix, and `_handle_leader_error`
always disagrees on that class — which is what forces consensus to rotate to a
different leader.

So the same rejection surfaces two different ways:

| | direct mode | live network |
|---|---|---|
| only the leader runs | the leader's raise propagates as a **clean revert** | — |
| validators participate | — | validators disagree, leaders **rotate**, and the transaction ends **undetermined** |

Both are safe: no program is admitted and no state changes. But every direct-mode
test that asserts `expect_revert()` on a bad compilation is observing the
leader-only shape. On a live network a rule that simply cannot be expressed in this
grammar will burn its rotations and finish undetermined rather than returning a
descriptive error to the owner.

## Example usage

Deploy a policy. The rule, the field schema and the acceptance vectors are all
fixed here and can never be edited:

```bash
genlayer deploy --contract contracts/compiled_policy.py --args \
  "Bounty submission rules" \
  '["The submission must be at least 200 words long.",
    "The submission must be written in English.",
    "The submission must include tests.",
    "The writing must be clear and respectful in tone."]' \
  '[{"name":"word_count","kind":"int"},{"name":"language","kind":"str"},
    {"name":"has_tests","kind":"bool"},{"name":"body","kind":"str"}]' \
  '[{"payload":{"word_count":500,"language":"English","has_tests":true,"body":"a careful writeup"},"expect":"PASS"},
    {"payload":{"word_count":10,"language":"English","has_tests":true,"body":"brief"},"expect":"FAIL"},
    {"payload":{"word_count":500,"language":"French","has_tests":true,"body":"bon travail"},"expect":"FAIL"}]'
```

Compile once (owner only), then evaluate for free forever:

```bash
genlayer write   <policy> compile_policy
genlayer call    <policy> evaluate '{"word_count":10,"language":"English","has_tests":true,"body":"brief"}'
# {"policy_digest":"...","policy_version":1,"residual":[],"verdict":"FAIL","violated":["1"]}
```

Consume it from your own contract — synchronously, inside your deterministic
region, with no equivalence principle of your own:

```python
result = json.loads(str(gl.get_contract_at(self.policy).view().evaluate(payload_json)))
require(result["verdict"] == "PASS", "policy did not pass: " + result["verdict"])
```

`contracts/gated_vault.py` is a ~150-line reference consumer that does exactly
this and binds the verdict to a real native GEN transfer. It runs no
non-deterministic block of its own — all of its judgement is inherited from the
policy it points at, which is the point of separating the two.

> **`GatedVault` has no refund, cancel or timeout path.** It is a minimal
> illustration of the integration shape, not production escrow. Once funded, the
> balance can leave only through a `PASS` verdict: if the policy is never
> compiled, or never passes for any payload the funder can construct, or is
> frozen in such a state, **the funds are locked permanently**. Anyone adapting it
> should add an owner-refund or expiry path before holding real value. The
> deliberate omission keeps the reference contract small enough to read in one
> sitting.

## Reuse

`CompiledPolicy` is a gate other contracts read. Store its address, call
`evaluate()`, act only on `PASS`. It is useful anywhere a rule is written for
humans but has to be enforced by code:

- eligibility and allow-list rules that non-programmers need to read and amend
- listing or admission criteria for a registry or marketplace
- contribution and bounty standards
- agent operating limits, where the limits must be auditable prose
- compliance checks whose rule text is the authoritative artefact

The win is the cost and trust inversion: one consensus round pins the rule down,
and every enforcement after that is deterministic and free. Change the
mechanisation and every consumer picks it up at once, with the digest telling them
it changed.

## Running the tests

Direct mode is the default: in-process, no network, no model, no Docker.

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt        # genlayer-test==0.29.2, genvm-linter==0.11.0
pytest -q                  # 71 tests, ~10 seconds
genvm-lint check contracts/compiled_policy.py
genvm-lint check contracts/gated_vault.py
```

Tool versions are pinned exactly, because newer genvm releases changed the runner
layout both tools use to resolve an SDK. The first `pytest` run downloads roughly
128 MB of genvm artifacts and takes a few minutes; later runs are instant.

**If `genvm-lint check` reports `Failed to load SDK: filename
'runners/py-genlayer/1j/...tar' not found`**, the linter has cached a newer genvm
release that no longer ships `py-genlayer` runners in the expected layout. Fetch
the release that contains this contract's pinned runner and move the newer tarball
out of the cache so the linter falls back to it:

```bash
genvm-lint download -v v0.3.0-rc7
mv ~/.cache/genvm-linter/genvm-universal-genlayerlabs-genvm-manager-*.tar.xz* /tmp/
```

The direct-mode runner resolves the same way, which is why `conftest.py` pins
`SDK_VERSION = "v0.3.0-rc7"` explicitly. See `DECISIONS.md`, "Direct-mode SDK
resolution has to be pinned explicitly".

The interesting tests use `direct_vm.run_validator()`, which replays the captured
validator closure so validator behaviour is **demonstrated, not asserted in
prose**. Swapping the LLM mock between the contract call and `run_validator()`
simulates a validator that compiled something different:

```python
direct_vm.mock_llm(r"compiling a rule", json.dumps(FAITHFUL))
policy.compile_policy()                       # leader admitted >= 200

direct_vm.clear_mocks()
direct_vm.mock_llm(r"compiling a rule", json.dumps(slack))   # validator compiles >= 150
assert direct_vm.run_validator() is False     # and rejects the leader
```

Agreement and disagreement are both covered:

| Test | Asserts |
|---|---|
| identical compilation | validator agrees |
| `not(x < 200)` vs `x >= 200` | agrees — equivalent, different shape |
| `forbid x < 200` vs `require x >= 200` | agrees — equivalent, opposite effect |
| `x >= 150` vs `x >= 200` | **rejects** — passes the vectors, differs behaviourally |
| `x >= 0` | rejects — fails the acceptance vectors |
| a mechanisable clause moved to residual | rejects — split disagrees |
| leader result malformed / not JSON | rejects |
| leader errored where the validator did not | rejects, forcing leader rotation |

The residual binding has its own regression tests, and they were **mutation-tested**
to prove they detect the old vulnerable behaviour rather than passing incidentally:
`adjudicate` was temporarily reverted to send a substituted question, both tests
failed, and both passed again once reverted.

| Test | Asserts |
|---|---|
| `test_the_substituted_residual_question_exploit_is_inexpressible` | the exact rejected exploit is refused at compile time |
| `test_an_admitted_program_carries_no_residual_wording` | admitted residual clauses have keys exactly `["id","kind"]` |
| `test_adjudication_judges_the_immutable_clause_text` | the immutable prose reaches the adjudicator |
| `test_a_substituted_question_never_reaches_the_adjudicator` | the substituted wording does not |

Integration tests run against a live endpoint:

```bash
gltest --network studionet tests/integration
```

## Verification status

Both suites have been run against the current source. Stated precisely, because the
distinction matters.

**Direct mode -- 71 tests, ~10s, no network, no model.** Covers the deterministic
core, all five verdicts, the three structural/behavioural gates, versioning, access
control, idempotency, digest binding, the residual-binding regression tests, and
validator agreement *and* disagreement via `run_validator()`.

**Studionet -- 6 integration tests, three consecutive green suites** (245s, 220s,
223s) against `https://studio.genlayer.com/api` (chain id `61999`) with a real model
and a real validator set, plus a separate evidence run that captured the lifecycle
below. Zero skips, zero assertion failures.

### Live evidence (current)

Deployed from the source in this repository. The deployed code was fetched back with
`gen_getContractCode` and is **byte-identical** to `contracts/compiled_policy.py`
(sha256 `740f263501cf5fb78b19d547c44bf0a6e7ca0c72a1ab7431f859c9640aeb28bb`, 50,901
bytes), which is what proves the fixed logic is the logic running on chain.

| What | Evidence |
|---|---|
| CompiledPolicy contract | `0x8a0535eD57C455ADD0acB20206AAF1582730AD13` |
| `compile_policy()` | tx `0x027f06920fe51162c24c9d68c9bcede55337709b0791bb088931c3558e84b4c6`, FINALIZED |
| Admitted digest / version | `eb930c478c1d1405a5454533608e39054ba6d86af7447dfba7cf4b12f21f9aae`, v1 |
| `adjudicate()` | tx `0x4028add0ed17c5883cc2ef8657502838b62466b57ea74a75343068d12494a41b`, FINALIZED |
| GatedVault contract | `0x660DcE4B754744100cF04012a45B3DA07798b60c` |
| `fund()` | tx `0x4312334b904376f8decedd3e89fa47ba3ed364b4530f0f188771fec9e6b95930`, FINALIZED |
| `release()` on a failing payload | tx `0x12a49084f1e12edc64ac37ae7d0e51661200ac8f2cbc22b9c3946b233a72ada0`, correctly **rejected**; escrow untouched at 1000 |
| `release()` on a passing payload | tx `0x8dd56e86ad5bdd9449f2a965db0c6b2a0691f5fd2846540a8bad377fc5f88edb`, FINALIZED |
| `withdraw()` | tx `0xd128ef08fc24be704af205ee9cfc07c04d0abb2f72caf386a87731cdc2079579`, FINALIZED, outbound message `value: 1000` |

All six transactions report `FINALIZED` via `gen_getTransactionStatus`, and both
contract ABIs resolve via `gen_getContractSchema` (8 and 6 methods).

**A real model produced exactly the faithful mechanisation, in the new
representation** -- `word_count >= 200`, `language == "English"`,
`has_tests == true`, and clause 4 declared residual as `{"id": "4", "kind":
"residual"}` with **no** question, restatement or reason field. Verified on chain:
`residual_carries_only_id_and_kind: true`, and the serialised program contains no
`question` substring at all. No prompt iteration and no weakening of validation was
needed to get this; the model complied on the first attempt.

All three acceptance vectors then returned the right verdict with the right violated
clause id, the residual ruling came back `PASS` with `stale: false` bound to the
current digest, a failing payload was refused with the escrow intact, a second
`release` was refused, and the vault went `held 1000 -> 0`, `claimable 1000 -> 0`.

This also confirms three surfaces direct mode cannot reach: the synchronous
cross-contract read, `preview()` as a **view calling another contract's view**, and a
real native GEN transfer via `emit_transfer`.

### Reproducing the live reads

The stored ruling is keyed by `(policy_version, payload)`, so it resolves only for
the exact payload the evidence run used:

```python
GOOD = {"word_count": 500, "language": "English", "has_tests": True,
        "body": "Thanks for reviewing. Fixes an off-by-one in pagination; tests added."}
# payload digest 9ebe4eccc2ae9a70cf4f6456a8e8302b5c08311451dd6fe3cef5742bd4a2f08a
```

Against the deployed contracts this returns:

```
policy.status()          -> compiled: true, policy_version: 1, ruling_count: 1,
                            policy_digest: eb930c47...9aae
policy.program()         -> the three predicates above, plus {"id":"4","kind":"residual"}
policy.evaluate(GOOD)    -> {"verdict":"RESIDUAL_REQUIRED","residual":["4"]}
policy.ruling_for(GOOD)  -> {"rulings":[{"id":"4","satisfied":true}],
                             "stale":false,"verdict":"PASS"}
vault.preview(GOOD)      -> "PASS"
vault.status()           -> released: true, held: 0, last_verdict: "PASS"
```

Substituting `word_count: 10` returns `{"verdict":"FAIL","violated":["1"]}` --
deterministic enforcement readable on-chain with no model in the loop.

### Superseded deployment (history, not current evidence)

The first deployment implemented the earlier design in which a residual clause
carried compiler-authored wording. That design was rejected for the reason set out
in "Residual clauses are bound to the immutable rule", and the contracts are not
upgradable, so it was replaced rather than patched. These identifiers are retained
only so the record is complete. **They must not be cited as evidence for the current
contract.**

| Superseded | Identifier |
|---|---|
| CompiledPolicy (old) | `0x9B4C7d682D1a89C53cb2Dc5aF1359e5cb33DF294` |
| GatedVault (old) | `0x8759c4dA2208ED29eF62F935E9FE390031173163` |
| compile (old) | `0x5be55335175dc8efc31d1d879492229f49b18f174d5f867c0a2f2027e11546da` |
| adjudicate (old) | `0xd6210f85109868f741fca55ac4e7a814f7e183b1d2a9554726351ca051024c7d` |
| fund (old) | `0xdd8e49c37d9f79c9b1629ed87495838b23f82ba1a3adb00227379ccdb45caf8a` |
| release, refused (old) | `0x703d12ac4fe1988adcfb0124b1d21c9241fb76c5ee0ab771864487ce2dcd77c3` |
| release (old) | `0xd3cf6792dae585098dba3db552a810fe8bbceca9974ca0921f0d1c3395c830f7` |
| withdraw (old) | `0x21f3c2c77c1ccb92d647c7d46fe7e126cd52576b0d8e096104d56a42637a7f83` |

**Still unverified, stated plainly:**

- **Only Studionet has been exercised.** Asimov and Bradbury are untested, and Studio
  is documented as diverging from a live network on gas, ghost contracts and EVM
  interaction.
- **The appeal path has not been exercised.** `adjudicate()` is idempotent per
  `(policy_version, payload)` specifically so an appeal re-execution cannot
  double-append or double-credit, but no transaction here was appealed.
- **The compilation success rate is empirical, not a reliability proof.** Three green
  suites plus one evidence run is four data points on one rule with one validator mix.
  A different model, mix or rule could fail to compile -- and the honest failure mode
  is a *rejected* compilation, never a bad admission.
- **Behavioural equivalence is probe-bounded** (at most 96 deterministic probes), so
  it is checked, not proven. Two programs differing only on a combination no probe
  reaches would be treated as equivalent.
- **`gen_call` rejects string arguments above roughly 200 bytes** with an RLP
  length-prefix error. This is a client/node bug, not a contract one -- the same
  argument passes through the write path and through a contract-to-contract call --
  but it does limit RPC-facing payloads today. A *large* payload through a
  contract-to-contract call remains unconfirmed end to end.

`DECISIONS.md` keeps the full record, including the failures that were observed and
their classification.

One environmental note, since it affected several runs: this development environment
suffers intermittent DNS resolution failures for `studio.genlayer.com`
(`Temporary failure in name resolution`). Those runs produced **zero** assertion
failures -- the transactions that had already landed were correct -- and were re-run
unchanged. No code, prompt or assertion was altered in response to any failure.

## Deploying

```bash
npm install -g genlayer
genlayer network studionet          # or localnet / testnet-asimov
genlayer deploy --contract contracts/compiled_policy.py --args ...
```

The runner is pinned to `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`,
which is the hash the whole test suite and both linter validations ran against.
The linter reports that a newer runner exists; switching to it made the direct
suite fail to load, so it was not adopted. See `DECISIONS.md`.

## Layout

```
contracts/compiled_policy.py   the primitive
contracts/gated_vault.py       minimal reference consumer (not a second primitive)
tests/direct/                  71 tests: no network, no model, ~10s
tests/integration/             6 Studionet tests (3 green suites; see Verification status)
CONTRACT.md                    one-page specification
DECISIONS.md                   design record and live runner findings
```

## Limitations

Stated because they are real, not because they are comfortable.

- **`evaluate()` over JSON-RPC is limited to small payloads today.** `gen_call`
  rejects string arguments above roughly 200 bytes with an RLP length-prefix error.
  This is a client/node bug, not a contract one — the same argument passes fine
  through the write path and through a contract-to-contract call, and deploys carry
  far larger arguments without trouble. It was isolated with a size sweep; the
  evidence is in `DECISIONS.md`. Keep RPC-facing payloads small until it is fixed
  upstream. The primary reuse path (contract-to-contract) showed no such limit.
- **Behavioural equivalence is checked on a bounded probe set, not proven.** The
  probes are boundary values around every literal in both programs plus a
  lockstep sweep, capped at 96. Two programs that differ only on an input
  combination no probe reaches would be treated as equivalent. Adding an
  exhaustive check is not possible in general; widening the probe set is.
- **Residual clauses fall back to per-payload judgement**, so a rule that is
  mostly subjective gets little benefit. A program that mechanises nothing is
  refused outright rather than pretending. And with a small payload there may be
  little for the model to judge, which makes the residual ruling genuinely
  variable between runs — the integration test asserts both outcomes rather than
  betting on one.
- **A rule whose clauses cannot be expressed in this grammar will not compile.**
  That is the intended failure, but it does bound the applicable rules.
- **The prose rule is immutable after deployment.** Amending a rule means a new
  deployment. This is a deliberate trade for the guarantee that every
  mechanisation is judged against the same public acceptance vectors.
- **`compile_policy()` is owner-gated.** The owner cannot force a bad program
  past the gates, but can choose *when* to recompile.
- **`GatedVault` can lock funds permanently** — see the warning above. It is a
  reference consumer, not production escrow.

## License

MIT — see [`LICENSE`](LICENSE).
