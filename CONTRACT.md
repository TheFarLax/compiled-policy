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
3. **Differential, deterministic.** Validator compiles independently, requires an
   identical mechanised/residual split, and compares verdict vectors over a probe
   set derived from the literals of both programs.

All three run inside the validator *and* again in the deterministic region after
consensus returns, so an admitted program passed every gate on every node that
looked at it.

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

**Verified live.** CompiledPolicy `0x8a0535eD57C455ADD0acB20206AAF1582730AD13`,
digest `eb930c478c1d1405a5454533608e39054ba6d86af7447dfba7cf4b12f21f9aae`, v1.
Compile tx `0x027f06920fe51162c24c9d68c9bcede55337709b0791bb088931c3558e84b4c6` and
adjudication tx `0x4028add0ed17c5883cc2ef8657502838b62466b57ea74a75343068d12494a41b`,
both FINALIZED. The deployed code was fetched with `gen_getContractCode` and is
byte-identical to `contracts/compiled_policy.py`. A real model emitted the residual
clause as `{"id":"4","kind":"residual"}` with no extra field. The earlier policy at
`0x9B4C7d682D1a89C53cb2Dc5aF1359e5cb33DF294` is **superseded**.

**Limits.** Behavioural equivalence is probe-bounded, not proven. Subjective
rules degrade to per-payload adjudication. The prose rule cannot be amended after
deployment. `evaluate()` cost grows with program size, which the node cap bounds.

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
