"""Load `contracts/compiled_policy.py` as a plain Python module.

The equivalence proof makes a completeness claim -- that a finite set of
abstract states covers the whole payload space -- and a claim like that can only
be checked by enumerating a concrete payload space and comparing. Direct mode
runs the contract inside WASM and exposes only its public methods, so the
internals are unreachable from there.

This loads the SHIPPED SOURCE, unmodified, against a stub of the runner surface
the module touches at import time. It is a test-only loader: nothing here is
deployed, and the functions under test are the real ones, not a reimplementation
that could drift from them.
"""

import sys
import types
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "compiled_policy.py"


class StubUserError(Exception):
    """Stands in for `gl.vm.UserError`, which carries `.message` on the pinned
    runner (verified live -- see DECISIONS.md)."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _stub_genlayer():
    gl = types.SimpleNamespace()
    gl.vm = types.SimpleNamespace(UserError=StubUserError, Return=object)
    gl.nondet = types.SimpleNamespace()
    gl.public = types.SimpleNamespace(write=lambda f: f, view=lambda f: f)
    gl.Contract = type("Contract", (), {})

    module = types.ModuleType("genlayer")
    module.gl = gl
    module.Address = str
    module.u256 = int
    module.DynArray = dict
    module.TreeMap = dict
    module.allow_storage = lambda cls: cls
    module.__all__ = ["gl", "Address", "u256", "DynArray", "TreeMap", "allow_storage"]
    return module


def load():
    """Exec the contract with the stub installed, then put `sys.modules` back.

    The stub must NOT outlive this call: the direct-mode tests in the same
    pytest session import the real `genlayer` from the runner, and leaving a
    stub behind would silently hand them a fake VM. The loaded module keeps its
    own reference to the stub `gl` through its globals, so restoring here costs
    nothing."""
    previous = sys.modules.get("genlayer")
    sys.modules["genlayer"] = _stub_genlayer()
    try:
        module = types.ModuleType("compiled_policy_under_test")
        source = CONTRACT.read_text(encoding="utf-8")
        exec(compile(source, str(CONTRACT), "exec"), module.__dict__)
    finally:
        if previous is None:
            sys.modules.pop("genlayer", None)
        else:
            sys.modules["genlayer"] = previous
    return module


cp = load()
UserError = StubUserError
