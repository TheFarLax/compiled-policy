"""Shared pytest configuration.

`SDK_VERSION` pins the genvm release the direct-mode runner loads. The runner's
default resolution follows the latest GitHub release, and the current latest no
longer ships `py-genlayer` runners in the layout the loader expects, so the
version that contains our pinned runner hash is named explicitly. See
DECISIONS.md, "direct-mode SDK resolution".
"""

from pathlib import Path

import pytest

SDK_VERSION = "v0.3.0-rc7"
CONTRACTS = Path(__file__).parent / "contracts"


@pytest.fixture
def deploy(direct_vm, direct_deploy):
    """Deploy a contract from contracts/ against the pinned runner."""

    def _deploy(name, *args):
        return direct_deploy(str(CONTRACTS / name), *args, sdk_version=SDK_VERSION)

    return _deploy
