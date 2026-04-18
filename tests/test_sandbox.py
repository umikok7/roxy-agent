from __future__ import annotations

import pytest

from harness.sandbox.runtime import BasicSandbox, SandboxPermissionError


def test_sandbox_rejects_outside_path(tmp_path):
    sandbox = BasicSandbox(tmp_path)

    with pytest.raises(SandboxPermissionError):
        sandbox.read_file("../outside.txt")
