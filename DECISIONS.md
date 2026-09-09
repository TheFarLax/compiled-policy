# DECISIONS

A record of the non-obvious choices behind `CompiledPolicy`, and of what was
verified **live against the pinned runner** rather than taken from documentation.
Newest first. Not a changelog; git history covers that.

---

## 2026-09-09 -- canonical deployment: one policy exercising the whole grammar

**Result.** The showcase deployment. One CompiledPolicy carrying a single
coherent rule that reaches every capability the contract implements, and one
GatedVault bound to it. Source unchanged from `4a090fc`; this entry records a
deployment, not a code change.

| | |
|---|---|
| CompiledPolicy | `0xbfb3B521FA3d8104BBb7A1aA388Bb5A1Ce435f1C` |
| GatedVault | `0x2c5895Bc7e6146c6633c4727247b8a0b0F6b850b` |
| policy digest | `dc39e5060d7f3f8f518f4516aca773225e5893650004594b78367730b27486db`, v1 |
| policy owner | `0x42586C842f87cFd2b4f5a34Af4F21b7906ed2ae3` |
| vault owner / beneficiary | `0xd62D9941b7782ea0c13Ce38B97EFcee95da6a3Dc` |

Transactions, all `ACCEPTED`, all `leader_only=false`, all one round, five
validators, **zero disagreements** throughout:

| step | tx |
|---|---|
| policy deploy | `0x4ccf2d124eac55a6639b7e5125d6bc5410804e18c8d76e3f8821f68572b1842f` |
| compile | `0xe2a74aee28b83a7c8dac8bccd1193bae1b138e45a1565676da0778d8dec4659c` |
| adjudicate (polite payload) | `0x577aac7ebf9d56bda6e3555fdeac408b8220f7dc9138717320f6a0f6fe9cbf20` |
| adjudicate again (idempotent) | `0xdb878c1231f37ea52f3db05e4ac85a6e44fd0e29952eafa75295f959302c6008` |
| adjudicate (abusive payload) | `0x80f50ce80ccd8795d631d9741eead488d01434072c354b0f432cbd51e8adc0f2` |
| vault deploy | `0x1c8f6ada0af6a7834a9434e84b674d774a0f95e044f0f1e47329c8bcd4bc4ecd` |
| vault fund (1000) | `0x3e64b98c82856b8fc313566ab3ce7dede54a47c5ed858fef584182ad39402345` |
| release refused | `0x79e229315feccbbf281437111fb3f9dd34e48e53fb5e7dacdb0e2d3834aa5b85` |
| release succeeded | `0x344581df9ecee168c25544eb1202897089ce1432191be15a8ffa794262d0eb50` |
| second release refused | `0xfbc3e0f1c2384d877b620245fe8b77872babbe80a22179bb873825de8c72dca9` |
| withdraw | `0x6d75f78d088a32819830a052281e8b11b90a4b8e029ef7c7818b43408531a4ad` |

**The model chose `in` where the rule said "or".** Clause 2 is prose — *"must
arrive through either the email channel or the web channel"* — and the compiler
emitted `in(channel, ["email","web"])` rather than `or(cmp eq, cmp eq)`. Both are
in the closed grammar, both are exactly abstracted, and the two are behaviourally
identical, so the equivalence proof treats them as the same program. Worth
recording because it is a reminder that the contract admits *behaviour*, not a
syntactic template: a check that pins the expected shape rather than the expected
semantics will report a false failure. Ours did, once, and the check was wrong.

**Residual binding, demonstrated rather than argued.** Two payloads differing
only in tone were put through the same mechanised clauses. The polite one was
ruled `PASS` on clause 6, the abusive one `FAIL` — and since nothing mechanical
separates them, the only thing that could have produced the difference is the
clause text read back from `self.clauses`. The vault then refused the abusive
payload with `RESIDUAL_FAIL` through `preview`, which is the whole binding chain
visible from outside the contract.

**Cost of the proof on a realistic rule.** 14 abstract states — 2, 3, 4, 3, 2
across the five mechanised clauses — against caps of 2048 per clause and 16384
total. The `contains` families are what matter: clause 3 carries two patterns on
one field and costs 4 states, and the width is exponential in patterns per
field, which is why `_MAX_CONTAINS_PER_FIELD` exists.

---

## 2026-08-30 -- the residual-binding fix verified live; previous deployment superseded

**Result.** The fixed contract was deployed fresh to Studionet and the complete
lifecycle passed. Three consecutive full integration suites went green (245s, 220s,
223s), zero skips, zero assertion failures, plus a dedicated evidence run.

**The proof that matters.** A malicious leader program cannot be injected into a real
validator set, so "the exploit is closed on chain" was established a different way:
the deployed code was fetched back with `gen_getContractCode` and is **byte-identical**
to the local source.

```
deployed 50901 bytes | local 50901 bytes
sha256 both: 740f263501cf5fb78b19d547c44bf0a6e7ca0c72a1ab7431f859c9640aeb28bb
deployed contains 'must carry only id and kind': True
deployed contains '_clause_text(cid)':           True
deployed contains a stored "question" key:       False
```

So the code running on Studionet provably contains the rejection guard and the
immutable-clause binding, and provably does not contain the removed field.

**The real model complied with the tightened grammar on the first attempt.** The
admitted program, read back from chain:

```json
{"clauses":[
 {"id":"1","kind":"mechanised","effect":"require",
  "predicate":{"op":"cmp","field":"word_count","rel":"ge","value":200}},
 {"id":"2","kind":"mechanised","effect":"require",
  "predicate":{"op":"cmp","field":"language","rel":"eq","value":"English"}},
 {"id":"3","kind":"mechanised","effect":"require",
  "predicate":{"op":"cmp","field":"has_tests","rel":"eq","value":true}},
 {"id":"4","kind":"residual"}]}
```

`residual_carries_only_id_and_kind: true`, and the serialised program contains no
`question` substring. No prompt iteration and no relaxation of validation was needed.

**Current evidence.** All FINALIZED via `gen_getTransactionStatus`; both ABIs resolve.

| Step | Identifier |
|---|---|
| CompiledPolicy | `0x8a0535eD57C455ADD0acB20206AAF1582730AD13` |
| digest / version | `eb930c478c1d1405a5454533608e39054ba6d86af7447dfba7cf4b12f21f9aae`, v1 |
| compile | `0x027f06920fe51162c24c9d68c9bcede55337709b0791bb088931c3558e84b4c6` |
| adjudicate | `0x4028add0ed17c5883cc2ef8657502838b62466b57ea74a75343068d12494a41b` |
| GatedVault | `0x660DcE4B754744100cF04012a45B3DA07798b60c` |
| fund | `0x4312334b904376f8decedd3e89fa47ba3ed364b4530f0f188771fec9e6b95930` |
| release, refused | `0x12a49084f1e12edc64ac37ae7d0e51661200ac8f2cbc22b9c3946b233a72ada0` |
| release | `0x8dd56e86ad5bdd9449f2a965db0c6b2a0691f5fd2846540a8bad377fc5f88edb` |
| withdraw | `0xd128ef08fc24be704af205ee9cfc07c04d0abb2f72caf386a87731cdc2079579` |

Lifecycle detail: `fund` -> `held 1000`; `release(TOO_SHORT)` refused with `held`
still `1000` and `released: false`; `preview` returning `FAIL` then `PASS`;
`release(GOOD)` -> `held 0`, `claimable 1000`, `released: true`; a second `release`
refused; `withdraw` -> outbound message `value: 1000`, `claimable 0`. The ruling was
`{"id":"4","satisfied":true}`, `stale: false`, bound to the current digest.

**The previous deployment is superseded, not deleted.** `0x9B4C7d682D1a89C53cb2Dc5aF1359e5cb33DF294` and
`0x8759c4dA2208ED29eF62F935E9FE390031173163` implement the rejected design and always will; the contracts are not
upgradable, so replacement was the only option. Their identifiers are retained in
README under "Superseded deployment" so the record is complete, explicitly marked as
history rather than current evidence.

**Failures observed, classified, and not worked around.** Three runs during this
phase aborted on `Temporary failure in name resolution` for `studio.genlayer.com` --
transport/DNS, class 3. Each produced **zero** assertion failures; the tests that had
already executed passed. DNS was probed until it resolved 10/10, then the suite was
re-run unchanged. No code, prompt, assertion or validation was touched in response to
any failure, and no failure is hidden: the aborted run is recorded here precisely
because the temptation in that moment is to quietly retry and report only the green
result.

**How to apply.** When a fix cannot be demonstrated adversarially on a live network,
verify the deployed artefact instead. `gen_getContractCode` plus a hash comparison
turns "we fixed it locally" into "the fixed code is what is running", which is the
claim that actually matters.

---

## 2026-08-30 -- Portal rejection: the residual path was not consensus-bound. Fixed by deleting the field.

**The rejection, verbatim.** "The residual-clause path is not yet consensus-bound.
During compilation, validators compare only whether a clause is residual, while the
leader's generated question is stored unchecked and later becomes the wording
adjudicated for PASS or FAIL. Please bind each residual question to the original
immutable clause -- preferably derive it deterministically from that clause or
require validators to compare its exact canonical meaning -- before using the ruling
to authorize downstream actions."

**Valid, and it was the strongest available objection.** Confirmed against the
source before acting. `_kind_signature` compared `[[id, kind]]` only; `_eval_program`
treated a residual clause as an id, so the question could not influence a verdict
vector and gate 3 was structurally blind to it; `_validate_program` checked only that
the question was a non-empty string under 240 chars; `_canon_program` stored it
verbatim; and `adjudicate` built its prompt from that stored string while never
referencing `self.clauses` at all.

**The exploit.** Declare clause 4 -- "The writing must be clear and respectful in
tone." -- residual with `question: "Is the submission non-empty?"`. Structural gate
passes. Acceptance vectors pass. The split matches the validator's. Verdict vectors
match, because a residual clause cannot change one. Admitted. Every later
adjudication then rules on a question the rule never asked, returns PASS, and
`GatedVault` converts that into an irreversible GEN transfer.

The sharpest way to put it: the second consensus round was sound relative to its
input, but its input was never made sound. Both sides independently agreed on the
answer to the wrong question, so `validate_ruling` worked perfectly while enforcing
something the rule did not say.

**Decision: delete the field.** A residual declaration is now `{"id", "kind"}`. The
text adjudicated is read from `self.clauses` by id. Chosen over the two alternatives:

- *Include the question in `_kind_signature`.* Would require two independent LLM
  compilations to emit byte-identical prose. Would essentially never agree.
- *Add an LLM check that the question restates the clause.* Adds a new
  nondeterministic surface and replaces a deterministic guarantee with an opinion --
  the opposite of this project's rule of settling by execution where possible.

Deleting it **removes** a consensus surface rather than adding one: id and kind are
now a residual clause's entire content, so the gate-3 split comparison already covers
it completely. It also makes the "the rule is immutable" claim true in effect rather
than only literally, stops policy identity depending on model phrasing, and closes an
injection path where leader-authored text flowed into a later prompt.

`_validate_program` now **rejects** any extra field on a residual clause rather than
ignoring it, so the substitution is inexpressible rather than merely unused.

**Also corrected: a documentation claim, not just code.** README and CONTRACT.md
asserted there was "no default-allow branch anywhere" and that an over-permissive
program is "rejected by code". Both were false for residual clauses. My own
pre-deployment audit read `_kind_signature` and described it as comparing the
mechanised/residual split without noticing that the *content* of the residual
declaration was what later authorised. That is the more useful lesson than the bug:
a field that no gate reads is a field no gate protects.

**Tests, mutation-checked.** Four added:
`test_the_substituted_residual_question_exploit_is_inexpressible`,
`test_an_admitted_program_carries_no_residual_wording`,
`test_adjudication_judges_the_immutable_clause_text`,
`test_a_substituted_question_never_reaches_the_adjudicator`. The last two use two
ordered LLM mocks -- one matching the immutable clause prose, one catch-all answering
the opposite way -- so the verdict itself reveals which text reached the model.
To prove they have teeth rather than passing incidentally, `adjudicate` was
temporarily mutated to send the substituted question again: both tests failed, and
both passed once the mutation was reverted. Suite: 66 -> 71 tests, all passing.

**Consequence: the deployed evidence is superseded.** The contracts are not
upgradable and the rule is immutable per instance, so this requires a fresh
deployment. `0x9B4C7d682D1a89C53cb2Dc5aF1359e5cb33DF294` and
`0x8759c4dA2208ED29eF62F935E9FE390031173163` implement the rejected design and
always will. Every transaction hash recorded below documents that version. README now
carries an explicit warning to that effect, and the evidence must be regenerated
before resubmission.

**How to apply.** When a field is written by a nondeterministic actor and read by an
authorisation path, either a gate compares it or it must not exist. There is no third
option, and "it is in the digest" is not a gate -- a digest records what was agreed,
not that anything checked it.

---

## 2026-08-29 -- final verification state before publication

**Re-read from the network, not from an old log.** Every recorded transaction was
re-queried with `gen_getTransactionStatus`: all six now report **`FINALIZED`**
(they were `ACCEPTED` when submitted; the appeal window has since closed). Both
contract ABIs still resolve via `gen_getContractSchema`, and the deployed state was
read back directly:

```
policy.status()         -> compiled: true, policy_version: 1, ruling_count: 1,
                           policy_digest: 2a6161242df7a814a89cf7e95869202adaca2b7e63ead2a6699e369ed7ee5684
policy.program()        -> the admitted four clauses, clause 4 residual
policy.evaluate(short)  -> {"verdict":"FAIL","violated":["1"]}
policy.ruling_for(good) -> {"rulings":[{"id":"4","satisfied":true}],"stale":false,"verdict":"PASS"}
vault.status()          -> released: true, held: 0, last_verdict: "PASS"
vault.preview(good)     -> "PASS"
```

Reading the admitted program and a deterministic verdict off-chain a day later is
stronger evidence than any transaction hash: it shows the compiled policy persists
and still enforces without a model.

**One reproduction trap, now documented in README.** Rulings are keyed by
`(policy_version, payload)`. The evidence run used `body: "a careful writeup"`
(payload digest `783f450a...f3d2`); the integration test's body was later shortened
for the `gen_call` size limit. Replaying `ruling_for` with the test's payload
correctly returns `NO_RULING`, which a reviewer could easily misread as a broken
claim. Both cases were confirmed live and the exact reproduction payload is now
published.

**Pre-publication cleanup, in full.** `.claude/` added to `.gitignore`; `LICENSE`
(MIT) created to match the claim README already made; README updated with
`FINALIZED` statuses, the full refused-release hash, the reproduction payload, the
pinned tool versions, and the `genvm-lint` runner-cache workaround that would
otherwise make its own lint instructions fail on a fresh clone. `CONTRACT.md` gained
one sentence recording finality. No contract logic was touched: both contracts'
executable ASTs are unchanged.

**Verified absent before publication:** no `.env`, no keys, mnemonics, tokens or
wallet files anywhere outside `.venv/`; the only `ACCOUNT_PRIVATE_KEY_1` mentions are
`${...}` placeholders inside a comment in `gltest.config.yaml`; every 64-hex string
in the documentation was checked against the known public transaction-hash set (six
distinct, zero unexpected). Caches, `artifacts/`, `.venv/` and `.claude/` are all
ignored.

**How to apply.** Re-read transaction status and live contract state before quoting
either in a submission. Hosted Studio state can be reset, so any claim about a
deployed address should be re-checked rather than trusted from a log.

---

## 2026-08-28 -- Studionet integration suite passed; the whole lifecycle is now live evidence

**Result.** `gltest --network studionet tests/integration` collected 6 tests and
passed all 6 in 5m27s against `https://studio.genlayer.com/api` (chain id `61999`,
confirmed by `eth_chainId` returning `0xf22f`). A separate one-off evidence run
then captured addresses, transaction hashes and final state. The direct suite is 66
tests passing in ~13s, and both contracts pass `genvm-lint check` (lint plus SDK
validation).

| Step | Evidence |
|---|---|
| `CompiledPolicy` deployed | `0x9B4C7d682D1a89C53cb2Dc5aF1359e5cb33DF294` |
| `compile_policy()` | `0x5be55335175dc8efc31d1d879492229f49b18f174d5f867c0a2f2027e11546da`, ACCEPTED |
| digest / version | `2a6161242df7a814a89cf7e95869202adaca2b7e63ead2a6699e369ed7ee5684`, v1 |
| `adjudicate()` | `0xd6210f85109868f741fca55ac4e7a814f7e183b1d2a9554726351ca051024c7d`, ACCEPTED |
| `GatedVault` deployed | `0x8759c4dA2208ED29eF62F935E9FE390031173163` |
| `fund(value=1000)` | `0xdd8e49c37d9f79c9b1629ed87495838b23f82ba1a3adb00227379ccdb45caf8a` |
| `release(TOO_SHORT)` | `0x703d12ac4fe1988adcfb0124b1d21c9241fb76c5ee0ab771864487ce2dcd77c3`, correctly **rejected** |
| `release(GOOD)` | `0xd3cf6792dae585098dba3db552a810fe8bbceca9974ca0921f0d1c3395c830f7`, ACCEPTED |
| `withdraw()` | `0x21f3c2c77c1ccb92d647c7d46fe7e126cd52576b0d8e096104d56a42637a7f83`, ACCEPTED |

**The compilation a real model produced**, admitted by real validators:

```json
{"clauses": [
  {"id":"1","kind":"mechanised","effect":"require",
   "predicate":{"op":"cmp","field":"word_count","rel":"ge","value":200}},
  {"id":"2","kind":"mechanised","effect":"require",
   "predicate":{"op":"cmp","field":"language","rel":"eq","value":"English"}},
  {"id":"3","kind":"mechanised","effect":"require",
   "predicate":{"op":"cmp","field":"has_tests","rel":"eq","value":true}},
  {"id":"4","kind":"residual",
   "question":"Is the writing clear and respectful in tone?"}
]}
```

That is the faithful mechanisation, with the one genuinely subjective clause
correctly declared residual rather than mechanised or dropped. The three acceptance
vectors then returned `RESIDUAL_REQUIRED` / `FAIL violated:["1"]` /
`FAIL violated:["2"]` as required; the residual ruling came back
`{"id":"4","satisfied":true}`, `verdict: PASS`, `stale: false`; and the vault moved
`held 1000 -> 0`, `claimable 1000 -> 0` with the finalised receipt carrying an
outbound message of `value: 1000` to the beneficiary.

**Newly confirmed surfaces** that direct mode cannot reach: multi-validator
agreement on a compilation; multi-validator agreement on a residual ruling; the
synchronous cross-contract `view()` read; **`preview()` as a view calling another
contract's view** (previously flagged as the one construct I would not assume
works); and a real native GEN transfer through `emit_transfer`.

**What this is not.** One successful run on one network with one validator mix. It
does not establish a success *rate* for the compilation prompt, and it says nothing
about Asimov or Bradbury.

**How to apply.** Re-run the suite and re-record hashes after any change to the
prompt, the grammar, or the gates. A green direct suite is necessary but not
sufficient evidence that the primitive works.

---

## 2026-08-28 -- three further Studionet runs: 4/4 green on the final code, and what varies

**Why.** One green suite establishes that the primitive can work, not how often. The
suite was run three more times against unchanged contract logic to get a feel for the
compilation and adjudication success rate.

| Run | Result | Duration | Skips | Transport errors |
|---|---|---|---|---|
| earlier (final code) | 6 passed | 231s | 0 | 0 |
| +1 | 6 passed | 301s | 0 | 0 |
| +2 | 6 passed | 230s | 0 | 0 |
| +3 | 6 passed | 226s | 0 | 0 |

**Four consecutive full-suite runs on the final code, all green, no skips.** Because
each assertion is specific, a green run establishes more than "it worked":

- compilation was admitted by consensus, and the admitted program returned the correct
  verdict for all three acceptance vectors;
- the admitted program stayed inside the grammar with exact clause coverage and at
  least one mechanised clause;
- re-admission behaved correctly (either the digest guard refused an identical program
  or consensus admitted a genuinely different one);
- the compilation left clause 4 residual in every run -- the model never tried to
  mechanise a subjective clause and never dropped it;
- adjudication reached consensus, bound to the current digest with `stale: false`, and
  was idempotent on a second call;
- the residual ruling came back PASS, so the vault executed `release` and `withdraw`.

**What varies, honestly.** The residual ruling is the only observed source of
variation. With the earlier 17-character placeholder `body` it came back PASS once and
not-PASS once. With the current 69-character courteous sentence it was PASS in all four
runs. Four runs is not a stability proof, and the vault test asserts the refusal path
too precisely because this is expected to vary. The mechanised half never varied at all,
which is the point: once a program is admitted, enforcement is deterministic.

**Every failure ever observed, classified.**

| Failure | Class | Action taken |
|---|---|---|
| `Response ended prematurely` from `requests.post` | transport / network | none; re-ran |
| `gen_call ... RLP string ends with N superfluous bytes` | known client/node limitation | none in the contract; payload kept under the ceiling and the limit documented |
| vault test skipped when run with `-k` | test-quality defect | test made self-sufficient |

**Zero contract or application failures. Zero consensus disagreements on a
compilation.** No leader ever produced a program that validators rejected, and the
deterministic gates never rejected a real model's output.

**Caveat on the evidence.** `gltest` and `genlayer-py` do not log transaction hashes,
even at `--log-cli-level=DEBUG`, so per-run hashes were not captured for these three
runs; the recorded hashes come from the dedicated evidence run above. The per-phase
outcomes here are derived from which assertions passed, which is sufficient to
establish the success rate but is not a substitute for hashes.

**How to apply.** Treat compilation and consensus as reliable for a rule of this shape
and reserve the caution for the residual round, which is genuinely a judgement and
should never be asserted as PASS.

---

## 2026-08-28 -- `gen_call` rejects string arguments above roughly 200 bytes (client/node bug, not ours)

**Found by accident, isolated on purpose.** Lengthening the integration test's
`body` field to real prose (382 chars) turned a green suite red with
`gen_call failed (code=-32603): List length prefix announced a too small length`
and, at other lengths, `RLP string ends with N superfluous bytes`. Rather than
guess, a disposable probe swept the argument size against a freshly deployed
policy:

| `body` length | `evaluate()` over RPC |
|---|---|
| 17, 20, 40, 60, 80, 100, 120, 150, 180 | OK |
| 200 | fails: "RLP string ends with 256 superfluous bytes" |
| 300 | fails: "... 357 superfluous bytes" |
| 400 | fails: "List length prefix announced a too small length" |
| 600 | fails: "... 639 superfluous bytes" |

The error text tracks the argument length, which is the signature of a
length-prefix mismatch between encoder and decoder. The boundary sits between a
180-char and a 200-char body, i.e. roughly 210-230 bytes of total encoded
argument.

**It is confined to the RPC read path.** A second probe passed the same 631-byte
argument to a *write* (`adjudicate`) and to a write that performs a
cross-contract view internally (`GatedVault.release`): neither raised an encoding
error, both behaved exactly as the short-argument case did and reverted for the
expected business reason. Deploys carrying far more than 230 bytes of constructor
arguments have succeeded throughout. So: **writes are fine; `gen_call` views with a
long string argument are not.**

**Decision.** No contract change. The bug is in `genlayer-py 0.16.3` / the hosted
Studio RPC layer, and `_MAX_PAYLOAD` (4000) stays as the contract's own bound
because the contract is not what fails. The integration test keeps its payload at
142 bytes, well inside the working range, and the limitation is documented in
README.md so a consumer is not surprised.

**Consequence for reuse, stated honestly.** Calling `evaluate()` from an
application over JSON-RPC is currently limited to small payloads. Calling it
contract-to-contract -- which is the primary reuse path -- showed no such limit in
the probe above, but a cross-contract view with a *large* payload has not been
positively confirmed end to end, only that it does not raise an encoding error.

**How to apply.** Keep RPC-facing payloads small until this is fixed upstream, and
do not read a `gen_call` RLP error as a contract fault.

---

## 2026-08-28 -- the integration vault test was made self-sufficient

**Problem.** `test_vault_refuses_a_failing_payload_and_releases_a_passing_one`
originally skipped unless an earlier test in the same module-scoped fixture had
already adjudicated the residual clause. Running it with `-k` selected on its own
therefore silently skipped the money path -- the most important thing in the
suite. This was the hidden inter-test dependency flagged in the audit, and it bit
within an hour of being written down.

**Fix.** The test now adjudicates for itself when the verdict is
`RESIDUAL_REQUIRED` (safe: `adjudicate` is idempotent per
`(policy_version, payload)`), and if the residual ruling comes back FAIL it
asserts the *refusal* path instead -- the vault must refuse and the escrow must
survive. Both model outcomes are now covered, and nothing is asserted about which
one the model picks.

**Why this matters more than it looks.** With a short `body` (forced by the
`gen_call` limit above) the residual clause has little to judge, and the ruling
genuinely differed between runs: `satisfied: true` on 2026-08-28's first run,
`false` on the third. A test that asserted PASS would be flaky by construction.

---

Recorded because it is the useful part: the integration suite passed on the first
attempt with **zero changes to either contract**. The three-layer gate design, the
locals-capture discipline in the nondet closures, the canonicalisation, and the
`gl.vm.run_nondet_unsafe` / `gl.vm.Return` / `gl.vm.UserError(.message)` surface all
behaved on a live network exactly as the direct-mode probes predicted. The probe-first
discipline (deploy a throwaway contract and read the real surface before writing
against it) is what bought that.

---

## No contract change was needed at any point

Recorded because it is the useful part: the integration suite passed on the first
attempt with **zero changes to either contract**. The three-layer gate design, the
locals-capture discipline in the nondet closures, the canonicalisation, and the
`gl.vm.run_nondet_unsafe` / `gl.vm.Return` / `gl.vm.UserError(.message)` surface all
behaved on a live network exactly as the direct-mode probes predicted. The
probe-first discipline -- deploy a throwaway contract and read the real surface
before writing against it -- is what bought that.

Every change made after the first green run was to a **test or a document**, never
to contract logic: the vault test was made self-sufficient, the integration payload
was kept under the `gen_call` size ceiling, one missing `forbid` test was added, and
the limitations found along the way were written down.

---

## Runner surface probed live, not assumed

**What was done.** A throwaway probe contract pinned to
`py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` was deployed in
`gltest` direct mode and asked to dump its own SDK surface, because the published
documentation and the SDK reference disagree with each other in several places.

**Confirmed present on this runner:**

- `gl.vm` exposes **both** `run_nondet` and `run_nondet_unsafe`, plus
  `spawn_sandbox`, `unpack_result`, `Result`, `Return`, `UserError`, `VMError`,
  `ResultCode`, `Lazy`. So `run_nondet_unsafe` — the name used by the developer
  docs and by the `genlayer-dev` skill — is valid here, even though the SDK v0.3
  reference documents a rename. This contract uses `run_nondet_unsafe`.
- `gl.eq_principle` exposes `strict_eq`, `prompt_comparative`,
  `prompt_non_comparative`.
- `gl.vm.UserError("text")` constructs, and the instance carries **`.message`**.
  It does **not** carry `.data`, contradicting the SDK v0.3 source, which defines
  `UserError.data`. `_handle_leader_error` reads `.message` and guards with
  `hasattr` anyway.
- `gl.UserError` does **not** exist (`AttributeError`). Documentation examples that
  use it would fail on this runner.
- `gl.message` exposes exactly `chain_id`, `contract_address`, `origin_address`,
  `sender_address`, `value` — **no `datetime`**.
- `gl.message_raw` **does** contain `datetime`, plus `entry_data`, `entry_kind`,
  `entry_stage_data`, `is_init`, `stack`. So "there is no clock on this runner" is
  too strong a claim: there is no clock on `gl.message`, and there is one on
  `gl.message_raw`. This contract needs neither and reads neither.

**How to apply.** Do not reintroduce `gl.UserError` or `gl.message.datetime`.
Before trusting any documented attribute, deploy a probe and read it. Only a live
deploy is evidence.

---

## Contract sources must be pure ASCII, including comments

**Symptom.** After the equivalence rewrite, every integration test failed at
deploy with `ValueError: Failed to get schema from all clients (default, hosted
studio, and local)`. The deploy transaction itself succeeded — the address was
returned, and `gen_getContractSchema` on that address answered correctly over
plain HTTP — so the contract was on chain and loadable. Only the harness was
broken, and its error message named none of the three underlying causes.

**Cause.** `gltest`'s `ContractFactory._get_schema_with_fallback` swallows the
real exception from each client and reports only that all three failed. Forcing
the underlying error out revealed:

```
UnicodeEncodeError: 'ascii' codec can't encode character 'İ'
                    in position 9903: ordinal not in range(128)
```

`genlayer_py.contracts.actions.get_contract_schema_for_code` hex-encodes the
source with `eth_utils.encode_hex`, which encodes a `str` as ASCII. One
non-ASCII character anywhere in the file is fatal. The character was `U+0130` in
a **comment** — the worked example for why `len` cannot be proven, since it is a
letter whose lowercase form is two code points.

Two lesser traps found while chasing it: the Studio endpoint returns **HTTP 403**
to a bare `Python-urllib` User-Agent, so a hand-rolled probe can look like a
server-side outage when it is a WAF; and
`get_contract_schema_for_code` raises "not supported on this network" for any
chain that is not localnet, so on Studionet the *default* client never
contributes and the whole path depends on the hosted-studio fallback.

**How to apply.** Keep `contracts/*.py` pure ASCII, comments included. Write
`U+0130` rather than the character itself.
`test_contract_sources_are_pure_ascii` enforces this in direct mode, where it
costs milliseconds, instead of leaving it to a 40-second integration failure with
a misleading message. When `gltest` reports "failed to get schema from all
clients", call `get_contract_schema_for_code` directly to see the real
exception — the harness will not show it to you.

---

## Direct-mode SDK resolution has to be pinned explicitly

**Problem.** `gltest`'s direct runner resolves the SDK from the latest GitHub
genvm release. The current latest ships no `runners/py-genlayer/` directory in the
layout the loader expects, so every deploy failed with
`ValueError: No py-genlayer runners found in tarball`. The same happened to
`genvm-lint`, which reported `Failed to load SDK: filename
'runners/py-genlayer/1j/...tar' not found`.

**Decision.** `conftest.py` pins `SDK_VERSION = "v0.3.0-rc7"`, the release whose
tarball actually contains our pinned runner hash. For the linter, the incompatible
newer tarball has to be removed from `~/.cache/genvm-linter/` so it falls back to
the version that was downloaded with `genvm-lint download -v v0.3.0-rc7`.

**How to apply.** Treat both tools' default "latest" resolution as unreliable and
pin the version that contains the runner you pinned.

---

## The newer runner hash was tried and rejected

`genvm-lint` reports that `py-genlayer:1zr6nqk597d97kg0dyxg0shhrykx5v02zjgnyrajapy4wlqvfvwh`
is newer. Both contracts were switched to it and the direct suite was re-run: 3
failures and 64 errors, all `ImportError` at contract load. Reverted.

**How to apply.** The verified runner for this project is `1jb45aa8...`. A newer
hash existing is not a reason to adopt it; the suite passing on it is.

---

## Why a custom validator instead of `prompt_non_comparative`

The first design used `prompt_non_comparative` for the compile step, on the
reasoning that the input (prose + schema + vectors) is byte-identical on every
node, which is the documented sanctioned case for it.

**Rejected, for two reasons.** First, the official anti-pattern table is explicit
that extraction and classification decisions need comparative agreement on the
substantive result, and admitting a compilation is exactly that. Second, and more
decisive: equivalence of two predicate programs is a question that can be settled
by **executing them**, so handing it to an LLM would be throwing away a
deterministic answer. The validator compiles independently and proves the two
programs equivalent instead.

**Consequence.** The comparison logic is deterministic code, not a principle
string. It is unit-testable, it cannot hallucinate, and it does not depend on the
validator's model being good at reading code.

---

## Acceptance vectors are the anti-dodge mechanism

A compiler under pressure has two cheap escapes: emit a predicate that is true too
often, or declare the awkward clause `residual` and let a later judgement deal
with it. Both are closed deterministically:

- Every `FAIL` vector must fail **mechanically**. Reaching `RESIDUAL_REQUIRED` on a
  `FAIL` vector is treated as a failed compilation, which is what stops the
  route-everything-to-residual dodge.
- The constructor requires at least one `PASS` and one `FAIL` vector, so the gate
  can never be vacuous.
- At least one clause must be mechanised, so an all-residual program is refused.

**Why the vectors alone are not enough.** They are a finite public test set, and a
compilation can satisfy all of them and still be wrong — `word_count >= 150`
against a rule that says 200 is the worked example. That gap is what layer 3
exists for, and there is a test named after it.

---

## Probing was replaced by an exact proof

**What was there.** The differential comparison built a probe set from the
literals of both programs — integers contributed `v-1, v, v+1`, strings
themselves and a near-miss, `len` bounds strings that straddled them — swept one
field at a time plus a lockstep pass, capped at 96 payloads, and compared the
resulting verdict vectors. It was documented as bounded testing rather than a
proof.

**Why it was rejected.** A Portal review put the objection precisely: *different
programs can agree on every sampled payload and still return conflicting results
for an untested combination*. That is not a hypothetical.
`tests/proof/test_reviewer_objection.py` keeps a verbatim copy of the deleted
generator and runs it: for `word_count >= 200` against `word_count >= 200 and
word_count != 300`, it produced 18 probes and identical verdict vectors. It did
try `word_count == 300`, twice — but only with `has_tests: false`, where another
clause already forced `FAIL` and hid the difference. Widening the probe set was
not the fix, because the sampling strategy never paired the interesting value
with the field values that expose it.

The second specimen in that file is worse and settles the design question: a
clause widened only where another clause already fails produces an identical
whole-program verdict on **every** payload in existence. No verdict-vector
comparison of any size could catch it. The comparison therefore had to move from
whole-program verdicts to per-clause satisfaction.

**What replaced it.** An exact finite abstraction, per clause id, over the fields
both clauses mention:

- **bool** — the domain *is* `{True, False}`. Both enumerated.
- **int** — every int atom is `x rel k` or `x in K`, so its truth depends only on
  the sign of `x - k` for each mentioned constant `k`. The sign patterns
  partition ℤ into: below the minimum, each constant, each non-empty open gap,
  above the maximum. Every cell is non-empty; one representative from each.
- **str** — `cmp` eq/ne, `in` and `contains` all read `_norm(x)` and nothing
  else, so a string's behaviour is fixed by *(which normalised literal it equals,
  which mentioned patterns are substrings of it)*. Literal classes are
  represented by the literal itself, deduplicated by normalised form. Non-literal
  classes are indexed by the **substring-closed** subsets of the pattern set —
  `{abc}` without `{ab}` is unrealisable and is not invented. Each witness is
  built by joining the subset's maximal elements with a separator character that
  occurs in no pattern, so nothing can straddle a join, and is then **executed
  and checked** to realise exactly its intended class.

The Cartesian product covers every payload the schema admits, so executing both
clauses on every element and finding no disagreement *is* a proof of agreement
everywhere — for the declared grammar, and claiming nothing beyond it.

**`len` was removed rather than grandfathered.** It read the raw string while
every other string operator reads the normalised one, which breaks the "behaviour
is fixed by `_norm(x)`" property the string classes rest on. Unicode makes it
concrete: `str.lower()` is not length-preserving (`'İ'.lower()` is two code
points), so raw length and normalised content cannot share one set of
representatives. Sampling around length bounds concealed that; a proof cannot.
The operator went rather than the completeness claim.

**Fail closed, with no third branch.** `_MAX_STATES_PER_CLAUSE = 2048` and
`_MAX_STATES_TOTAL = 16384` are resource limits, never accuracy limits. Exceeding
one raises the contract's own `[LLM_ERROR]`, which lands on Disagree in the
validator and on a clean revert in the leader. `validate_compilation` returns
`True` only after a completed proof; there is no path from "too big to prove" to
"accepted", and no sampling code left to fall back to —
`test_no_probe_fallback_exists_in_the_contract` asserts the deleted symbols never
return.

**Verified, not asserted.** The completeness claim is checked against brute force
rather than argued: 660 random clause pairs, biased towards near-misses, each
decided both by the prover and by enumerating 7,678 concrete payloads with the
contract's own `_clause_satisfied` — 193 equivalent, 467 different, zero false
accepts and zero false rejects. Six deliberate mutations of the verifier
(`tools/mutation_check.py`) are all caught.

**Honest limit.** The proof is exhaustive *for this grammar*, not for programs in
general, and its completeness is a property of these operators reading only a
declared field's value. Adding an operator means extending the abstraction first.
A legal, correct program can also exceed the state budget and be refused — that
is the fail-closed side of the same rule.

---

## Canonicalisation is load-bearing

`and`/`or` operands and `in` values are sorted, clauses are sorted by id, and only
whitelisted keys survive the rebuild. Without this, two compilations that mean the
same thing would produce different digests, and a cosmetic reordering would look
like a new mechanisation.

Tested without needing two deployments: admit one operand ordering, then offer the
reverse. If canonicalisation works the digest is unchanged, so the contract must
refuse it as an identical program — which is what
`test_canonicalisation_makes_the_digest_shape_independent` asserts.

---

## No no-op version bumps

Re-admitting a byte-identical program is refused. A version counter anyone can
advance is a way to invalidate outstanding residual rulings, since rulings are
keyed by `(policy_version, payload)`. Combined with owner-only compilation, this
bounds the griefing surface to "the owner can publish a genuinely different
mechanisation", which is visible on-chain and carries a new digest.

---

## A test found a real robustness bug

`test_validator_rejects_a_malformed_leader_ruling` initially failed with a
`KeyError: 'rulings'` escaping `validate_ruling`. Behaviour was already safe — an
unhandled exception in a validator counts as Disagree — but the failure surfaced as
a raw traceback instead of a clean `False`. The membership and type check was moved
inside the guarded block. Recorded because the test earned its place.

---

## The model's aggregate verdict is discarded

`adjudicate()`'s prompt asks for an `overall` field. The contract never reads it:
the verdict is recomputed on-chain from the per-clause rulings, both inside the
leader function and again after consensus. A model cannot self-certify the
aggregate. `test_the_model_cannot_self_certify_the_aggregate` pins this.

---

## Prompt-injection posture

Clause prose and payload values are user-controlled and do reach the model. They
are fenced with an explicit inert-data delimiter and an instruction not to follow
instructions inside.

**That fencing is defence in depth only, and is not the real protection.** The real
protection is structural: nothing the model emits can widen `_OPS`, raise the node
or depth caps, add a field to the schema, or bypass the acceptance vectors, because
those are code constants checked after the model has spoken. A successful injection
can at worst cause a *rejected* compilation.

Deliberately **not** used: `eval()` of model-generated code inside
`spawn_sandbox`, which the official guidance offers as a pattern. A hand-written
interpreter over a closed JSON grammar is strictly safer and only ~40 lines.

---

## What has not been verified

Revised after the 2026-08-28 Studionet run. The items that moved to verified are
recorded in that entry; what remains open is below.

- **Compilation success *rate*.** One Studionet run produced a faithful program.
  That is evidence the prompt and grammar work, not a distribution. A different
  model, validator mix, or rule could fail, and the honest failure mode is a
  rejected compilation rather than a bad admission.
- **Other networks.** Only Studionet has been exercised. Asimov and Bradbury are
  untested, and Studio is explicitly documented as diverging from a live network on
  gas, ghost contracts and EVM interaction.
- **The appeal path.** No transaction here was appealed. `adjudicate()` is
  idempotent per `(policy_version, payload)` specifically so that an appeal
  re-execution cannot double-append or double-credit, but that guard has not been
  exercised against a real appeal.
- **Practical prompt/criteria size ceiling** on this runner. Unpublished, and the
  compile prompt embeds the full rule, schema and acceptance vectors, so a large
  rule could hit an undocumented limit.
- **The equivalence proof has a handful of live data points, not a rate.** Three
  distinct rules have been compiled and admitted on Studionet through the
  exhaustive gate with real models and real validator sets, the last reaching
  `contains` and `contains` under `or` at 14 abstract states. So the prover
  demonstrably accepts real model output on more than one rule shape. What
  remains unquantified is operational, not logical:
  how *often* two independent compilations of an arbitrary rule are provably
  equivalent, and whether the state budget is generous enough for the programs a
  model emits for a larger rule. The failure mode if not is a refused
  compilation, never a bad admission.
- **Proof scope.** Exhaustive for `and`/`or`/`not`, `cmp`, `in`, `contains` over
  `int`/`str`/`bool`. Not a claim about program equivalence in general, and not
  transferable to an operator added later without extending the abstraction.
- **`response_format="json"` under `prompt_comparative`.** Not used here; there are
  third-party reports of it misbehaving in that combination specifically. Unresolved
  and irrelevant to this contract.
- **`emit_transfer` re-entrancy semantics.** `GatedVault.withdraw` clears the ledger
  before emitting, which is safe under either interpretation. The live run confirmed
  the outbound message is constructed and the value lands; the ordering question
  itself was not probed.

## Known limitation left in deliberately

`GatedVault` has no refund, cancel or timeout path, so funded value is locked
permanently if the policy never passes. This is called out in README.md and
CONTRACT.md rather than fixed, because the contract's purpose is to be a readable
illustration of the integration shape. Anyone holding real value in it must add a
recovery path first.
