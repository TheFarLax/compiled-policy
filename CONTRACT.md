# CONTRACT.md — specification

One page per contract: purpose, the consensus move and why that one, state, API,
reuse, limits.

---

## CompiledPolicy — `contracts/compiled_policy.py`

**Purpose.** Turn a rule written in prose into a predicate program the validator
set admitted, so that every later evaluation is deterministic, free and
reproducible.

**Consensus move.** A custom leader/validator pair via
`gl.vm.run_nondet_unsafe` — not `prompt_non_comparative`, and deliberately so.
Admitting a compilation is an extraction-and-translation decision, and the
official guidance is explicit that those need agreement on the *substantive*
result rather than an allowed-label check. The validator therefore compiles its
own program and compares behaviour. `prompt_comparative` was also rejected: it
would hand the equivalence judgement to an LLM, when equivalence of two predicate
programs is exactly the thing that can be settled by *executing* them.

Three gates, in this order:

1. **Structural, deterministic.** Grammar whitelist, declared fields only,
   type-correct literals, node/depth caps, exact clause coverage, at least one
   mechanised clause.
2. **Behavioural, deterministic.** Every acceptance vector marked `FAIL` must
   fail mechanically; every `PASS` vector must not fail.
3. **Differential, deterministic, exhaustive.** Validator compiles independently,
   requires an identical mechanised/residual split, and then *proves* the two
   programs behave identically — clause for clause, on every payload the declared
   schema admits.

   This gate does **not** compare a finite sample of payloads. It constructs an
   exact finite abstraction of the supported payload semantics — one
   representative per behavioural equivalence class of each field, derived from
   the atoms of *both* programs — and compares the two programs exhaustively over
   every abstract state. Agreement on every abstract state is agreement on every
   payload, for the operators the grammar admits. If the abstraction does not fit
   the verifier's bounded resource limit, the compilation is **rejected rather
   than approximated**. There is no fallback to sampling.

Gates 1 and 2, and the constructibility of gate 3's abstraction, run inside the
validator *and* again in the deterministic region after consensus returns, so an
admitted program passed them on every node that looked at it. The comparison in
gate 3 needs two independently compiled programs and therefore runs only inside a
validator.

**Residual clauses are bound to the immutable rule.** A residual declaration is
`{"id", "kind"}` and nothing else; `adjudicate()` reads the text it judges back from
`self.clauses`, addressed by clause id. Because id and kind are the clause's entire
content, gate 3's split comparison covers it completely — nothing about a residual
clause escapes consensus. An earlier version let the compiler author a `question`
that was stored unchecked and later became the wording adjudicated for `PASS`; that
string was constrained by nothing, since residual clauses cannot influence a verdict
vector. Deriving the text from immutable storage removes the surface instead of
policing it.

**State.**

| Field | Mutability | Notes |
|---|---|---|
| `owner` | constructor | may compile and freeze |
| `title`, `clauses`, `schema`, `vectors` | **immutable** | no method writes to them |
| `program_json`, `program_digest` | replaced by `compile_policy` | canonical; `""` while uncompiled |
| `policy_version` | monotonic | bumps only on a *different* digest |
| `frozen` | one-way | closes recompilation only |
| `rulings`, `ruling_index` | append-only | `TreeMap[str, u256]` `1 + index` sentinel |

**API.**

| Method | Kind | Returns |
|---|---|---|
| `compile_policy()` | write, owner | canonical admitted program |
| `evaluate(payload_json)` | **view** | canonical verdict JSON |
| `adjudicate(payload_json)` | write | canonical ruling JSON; idempotent |
| `ruling_for(payload_json)` | view | stored ruling, or `NO_RULING`; carries `stale` |
| `freeze()` | write, owner | — |
| `status()`, `rule()`, `program()` | view | canonical JSON |

**Reuse.** `policy.view().evaluate(payload)` from any contract's deterministic
region; gate on `PASS`.

### Canonical deployment (Studionet)

The showcase deployment of this source. Both contracts run the code in this
repository at commit `4a090fc`, fetched back with `gen_getContractCode` and
compared byte for byte.

| | |
|---|---|
| CompiledPolicy | `0xbfb3B521FA3d8104BBb7A1aA388Bb5A1Ce435f1C` |
| GatedVault | `0x2c5895Bc7e6146c6633c4727247b8a0b0F6b850b` |
| policy digest | `dc39e5060d7f3f8f518f4516aca773225e5893650004594b78367730b27486db`, v1 |
| deploy tx | `0x4ccf2d124eac55a6639b7e5125d6bc5410804e18c8d76e3f8821f68572b1842f` |
| compile tx | `0xe2a74aee28b83a7c8dac8bccd1193bae1b138e45a1565676da0778d8dec4659c` |
| `compiled_policy.py` | sha256 `2a8c6cfba3eeb57212217bb2772e73d2c9a8189e59512102f071feaded11e407` |
| `gated_vault.py` | sha256 `328e2d8b9389bae418b578194e3a3d99bb539c9597e1a705c1560df3454256c2` |

The rule is a six-clause refund-triage policy. A real model mechanised five
clauses and left one residual, exercising `contains` (`body` mentions *refund*),
`contains` under `or` (*invoice* or *order*), string set membership (`channel in
{email, web}`), an int comparison (`account_age_days ge 30`) and a bool
comparison (`verified eq true`); the tone clause came back as
`{"id":"6","kind":"residual"}` with no extra field. Every compile and
adjudication ran with `leader_only=false` against a five-validator set with zero
disagreements. Exact equivalence needed 14 abstract states against caps of
2048 per clause and 16384 total.

Live behaviour on chain: each of the five mechanised clauses was individually
violated by a targeted payload and named alone in `violated`; an abusive but
mechanically clean payload reached `RESIDUAL_REQUIRED` and was ruled `FAIL` on
the tone clause, which is the residual binding working end to end. The vault
refused a failing release, released on the adjudicated payload, refused a second
release, and paid out. Full evidence is in DECISIONS.md.

Earlier addresses — `0x9B4C7d682D1a89C53cb2Dc5aF1359e5cb33DF294`,
`0x8a0535eD57C455ADD0acB20206AAF1582730AD13`, `0x7e5a1c70b2640E20E91b827781EfA086b3BFF596`
and `0x31472799Aa03c06F1d644cBbC872bdea50b9E7B9` — are **superseded**.

**Limits.** The equivalence proof is exhaustive **for the declared grammar** —
`and`/`or`/`not`, `cmp`, `in`, `contains`, over `int`/`str`/`bool` fields — and
claims nothing beyond it. Its completeness rests on those operators reading only
the value of a declared field, through `_norm` in the string case; an operator
that read a string some other way would need its own equivalence classes before
it could be admitted, which is why `len` was removed. Expressive programs can
exceed the state budget and be refused even though they are legal and correct.
Subjective rules still degrade to per-payload adjudication, and that path is
LLM-judged, not proved. The prose rule cannot be amended after deployment.
`evaluate()` cost grows with program size, which the node cap bounds.

**Deployment precondition.** Gate 3 is the only one that cannot be re-checked
after consensus, because it needs a second independent compilation. On a
leader-only network it therefore does not run at all, and a program that passes
the acceptance vectors but is subtly wrong would be admitted. Deploy only where a
real validator set participates.

**Failure shape differs by environment.** A rejection from any gate is raised with
an `[LLM_ERROR]` prefix, on which the validator always disagrees. In direct mode
(leader only) that surfaces as a clean revert; on a live network it rotates leaders
and the transaction ends undetermined. Safe either way — no program is admitted.

---

## GatedVault — `contracts/gated_vault.py`

**Purpose.** A minimal reference consumer, included to prove the integration
shape and to bind a policy verdict to an irreversible native GEN transfer. It is
**not** a second primitive.

**Consensus move.** None of its own. It performs a synchronous cross-contract
`view()` read in its deterministic region — every validator reads the same
committed policy state and computes the same verdict, so no equivalence principle
applies. Putting that read inside a nondet block would be a category error, and
GenVM forbids it.

**State.** `owner`, `policy`, `beneficiary`, `balance_held`, `released` (one-way),
`last_verdict`, `claimable: TreeMap[Address, u256]`.

**API.** `fund()` payable · `release(payload_json)` · `withdraw()` ·
`preview(payload_json)` view · `status()` view · `claimable_of(who)` view.

**Money design.** Pull payment: `release` credits the ledger, `withdraw` clears
the ledger and *then* emits the transfer. Release is one-way and closes the vault.

**Refusal semantics.** `UNCOMPILED`, `INVALID_PAYLOAD`, `FAIL`,
`RESIDUAL_NO_RULING`, `RESIDUAL_FAIL` and `RESIDUAL_STALE` all refuse. There is
no default-allow branch: only the exact token `PASS` releases funds, and a
residual ruling made under an older mechanisation is refused rather than honoured.

**No refund, cancel or timeout path — read this before reusing it.** Funded value
can leave only through a `PASS` verdict followed by `withdraw()`. If the policy is
never compiled, never passes for any payload the funder can construct, or is frozen
in such a state, **the balance is locked permanently**. There is no owner recovery,
no expiry and no cancel. This is a deliberate omission that keeps the reference
contract readable in one sitting; anything holding real value needs an
owner-refund or expiry path added first.

**Verified live.** Studionet: `fund` -> failing `release` correctly rejected ->
`preview` returning `PASS`/`FAIL` -> `release` -> `withdraw` emitting an outbound
message of `value: 1000` -> `claimable 0`. Contract
`0x660DcE4B754744100cF04012a45B3DA07798b60c`, wired to CompiledPolicy
`0x8a0535eD57C455ADD0acB20206AAF1582730AD13`. A second `release` was refused. Every
transaction in the sequence reports `FINALIZED`. This also confirms `preview()` works
as a view calling another contract's view, which direct mode cannot exercise.

The earlier vault at `0x8759c4dA2208ED29eF62F935E9FE390031173163` is **superseded**;
it was wired to the pre-fix policy. See README, "Superseded deployment".
