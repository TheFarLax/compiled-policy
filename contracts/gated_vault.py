# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
GatedVault -- a minimal REFERENCE CONSUMER of CompiledPolicy.

This is deliberately small and deliberately boring. It exists to prove one
claim: a CompiledPolicy is consumable from another contract's deterministic
region with a synchronous cross-contract read, and its verdict can be bound to
a real, irreversible native GEN transfer.

It is not a second primitive and it is not a product. Read it as documentation
of the integration shape.

HOW A CONSUMER USES THE PRIMITIVE
  1. Call `policy.view().evaluate(payload)` -- deterministic, free, no
     consensus, no model. Every validator computes the same answer.
  2. Act only on PASS.
  3. When the verdict is RESIDUAL_REQUIRED, look for a stored adjudication with
     `policy.view().ruling_for(payload)` and act only on a non-stale PASS.
  4. Treat UNCOMPILED, INVALID_PAYLOAD, FAIL, NO_RULING and any stale ruling as
     a refusal. There is no default-allow branch anywhere in this contract.

Note that this contract runs NO non-deterministic block of its own. All of its
judgement is inherited from the policy it points at, which is exactly the point
of separating the two.

NO REFUND, CANCEL OR TIMEOUT PATH -- READ BEFORE REUSING
  Funded value can leave only through a PASS verdict followed by withdraw(). If
  the policy is never compiled, never passes for any payload the funder can
  construct, or is frozen in such a state, the balance is locked PERMANENTLY.
  There is no owner recovery, no expiry and no cancel. That is a deliberate
  omission to keep this file readable in one sitting; anything holding real
  value needs a recovery path added first.

VERIFIED LIVE (Studionet, 2026-08-28)
  fund -> a failing release correctly rejected -> preview returning PASS/FAIL ->
  release -> withdraw emitting an outbound message of value 1000. This run also
  confirmed the two cross-contract surfaces direct mode cannot reach: a write
  calling another contract's view (release), and a VIEW calling another
  contract's view (preview). See DECISIONS.md for addresses and tx hashes.
"""

from genlayer import *
import json

ERROR_EXPECTED = "[EXPECTED]"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise gl.vm.UserError(message)


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


# Native GEN leaves this contract only through the chain layer, so the recipient
# is addressed through an EVM interface even when it is a plain account.
@gl.evm.contract_interface
class _NativeRecipient:
    class View:
        pass

    class Write:
        pass


class GatedVault(gl.Contract):
    owner: Address
    policy: Address
    beneficiary: Address
    balance_held: u256
    released: bool
    last_verdict: str
    claimable: TreeMap[Address, u256]

    def __init__(self, policy: Address, beneficiary: Address):
        zero = Address("0x0000000000000000000000000000000000000000")
        # Address-shaped calldata arrives already decoded on this runner, so
        # re-wrapping an Address in Address() must be avoided.
        pol = policy if isinstance(policy, Address) else Address(policy)
        ben = beneficiary if isinstance(beneficiary, Address) else Address(beneficiary)
        require(pol != zero, ERROR_EXPECTED + " policy address required")
        require(ben != zero, ERROR_EXPECTED + " beneficiary required")
        self.owner = gl.message.sender_address
        self.policy = pol
        self.beneficiary = ben
        self.balance_held = u256(0)
        self.released = False
        self.last_verdict = ""

    @gl.public.write.payable
    def fund(self) -> None:
        require(not self.released, ERROR_EXPECTED + " already released")
        require(int(gl.message.value) > 0, ERROR_EXPECTED + " send some value")
        self.balance_held = u256(int(self.balance_held) + int(gl.message.value))

    @gl.public.write
    def release(self, payload_json: str) -> str:
        """Release the escrow iff the policy says PASS.

        The cross-contract read happens here, in the deterministic region -- not
        inside a non-deterministic block. Every validator reads the same
        committed policy state and computes the same verdict, so this needs no
        equivalence principle of its own."""
        require(not self.released, ERROR_EXPECTED + " already released")
        require(int(self.balance_held) > 0, ERROR_EXPECTED + " nothing escrowed")

        verdict = self._verdict(payload_json)
        self.last_verdict = verdict
        require(verdict == "PASS", ERROR_EXPECTED + " policy did not pass: " + verdict)

        amount = int(self.balance_held)
        self.balance_held = u256(0)
        self.released = True
        self.claimable[self.beneficiary] = u256(
            int(self.claimable.get(self.beneficiary, u256(0))) + amount
        )
        return verdict

    def _verdict(self, payload_json: str) -> str:
        """Resolve a payload to a single token. Anything that is not an
        unambiguous PASS is a refusal; there is no default-allow path."""
        other = gl.get_contract_at(self.policy)
        result = json.loads(str(other.view().evaluate(payload_json)))
        verdict = str(result.get("verdict", ""))

        if verdict != "RESIDUAL_REQUIRED":
            return verdict

        # Residual clauses apply, so the mechanised half passed but a judgement
        # is still outstanding. Consult the stored adjudication; a ruling made
        # under an older mechanisation is refused, not honoured.
        ruling = json.loads(str(other.view().ruling_for(payload_json)))
        if str(ruling.get("verdict", "")) != "PASS":
            return "RESIDUAL_" + str(ruling.get("verdict", "NO_RULING"))
        if bool(ruling.get("stale", False)):
            return "RESIDUAL_STALE"
        return "PASS"

    @gl.public.write
    def withdraw(self) -> int:
        """Pull payment: adjudication and disbursement stay in separate
        transactions, and the ledger is cleared before the transfer is emitted."""
        who = gl.message.sender_address
        owed = int(self.claimable.get(who, u256(0)))
        require(owed > 0, ERROR_EXPECTED + " nothing to withdraw")
        self.claimable[who] = u256(0)
        _NativeRecipient(who).emit_transfer(value=u256(owed))
        return owed

    @gl.public.view
    def preview(self, payload_json: str) -> str:
        """Read-only dry run, so a caller can see why a release would fail.

        This is a view that calls another contract's view. Confirmed working live
        on Studionet (see the module docstring); direct mode cannot exercise it
        because it does not implement CallContract."""
        return self._verdict(payload_json)

    @gl.public.view
    def status(self) -> str:
        return _canon(
            {
                "owner": self.owner.as_hex,
                "policy": self.policy.as_hex,
                "beneficiary": self.beneficiary.as_hex,
                "held": int(self.balance_held),
                "released": self.released,
                "last_verdict": self.last_verdict,
            }
        )

    @gl.public.view
    def claimable_of(self, who: Address) -> int:
        addr = who if isinstance(who, Address) else Address(who)
        return int(self.claimable.get(addr, u256(0)))
