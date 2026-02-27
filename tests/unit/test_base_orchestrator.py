"""Tests for BaseOrchestrator shared logic (subprocess, HCL parsing, workspace)."""

import json
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

import pytest

from overtime.terraform.base import BaseOrchestrator
from overtime.terraform.state import TerraformOutputs
from overtime.utils.exceptions import TerraformError


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing abstract base
# ---------------------------------------------------------------------------


class _StubOrchestrator(BaseOrchestrator):
    """Minimal concrete subclass that satisfies all abstract methods."""

    def plan(self, config: Dict[str, Any]) -> None:
        pass  # pragma: no cover

    def apply(
        self, config: Dict[str, Any], *, auto_approve: bool = False
    ) -> TerraformOutputs:
        pass  # pragma: no cover

    def destroy(
        self, config: Dict[str, Any], *, auto_approve: bool = False
    ) -> None:
        pass  # pragma: no cover

    def get_vm_definitions(
        self, config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        pass  # pragma: no cover


SAMPLE_HCL = """\
locals {
  vm_definitions = {
    "ad-lab-m" = [
      { name_suffix = "ad-1a", role = "ad", os_type = "windows" },
      { name_suffix = "ad-2a", role = "ad", os_type = "windows" },
    ]

    "jumphost" = [
      { name_suffix = "lutil-1a", role = "lutil", os_type = "linux" },
    ]
  }
}
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def orchestrator(tmp_path) -> _StubOrchestrator:
    """Stub orchestrator pointed at a temp directory with sample HCL."""
    (tmp_path / "main.tf").write_text(SAMPLE_HCL)
    return _StubOrchestrator(terraform_dir=tmp_path)


# ---------------------------------------------------------------------------
# TestBaseOrchestrator — ABC enforcement
# ---------------------------------------------------------------------------


class TestBaseOrchestratorABC:
    """Verify that BaseOrchestrator cannot be instantiated directly."""

    def test_cannot_instantiate_directly(self, tmp_path):
        """BaseOrchestrator raises TypeError when instantiated without subclass."""
        with pytest.raises(TypeError, match="abstract method"):
            BaseOrchestrator(terraform_dir=tmp_path)


# ---------------------------------------------------------------------------
# TestRun — subprocess wrapper
# ---------------------------------------------------------------------------


class TestRun:
    """_run() subprocess invocation and error handling."""

    @patch("overtime.terraform.base.subprocess.run")
    def test_invokes_subprocess_with_correct_args(self, mock_run, orchestrator):
        """_run() shells out to ``terraform`` in the configured directory."""
        mock_run.return_value = MagicMock(returncode=0)
        orchestrator._run(["plan"], capture=True)

        mock_run.assert_called_once_with(
            ["terraform", "plan"],
            cwd=orchestrator.terraform_dir,
            capture_output=True,
            text=True,
            env=None,
        )

    @patch("overtime.terraform.base.subprocess.run")
    def test_passes_extra_env_to_subprocess(self, mock_run, orchestrator):
        """_run() merges _extra_env into the subprocess environment."""
        mock_run.return_value = MagicMock(returncode=0)
        orchestrator._extra_env["MY_SECRET"] = "s3cret"
        orchestrator._run(["init"], capture=True)

        call_env = mock_run.call_args.kwargs["env"]
        assert call_env["MY_SECRET"] == "s3cret"
        # Parent environment is also present
        assert "PATH" in call_env

    @patch("overtime.terraform.base.subprocess.run")
    def test_raises_terraform_error_on_nonzero(self, mock_run, orchestrator):
        """Non-zero exit code with check=True raises TerraformError."""
        mock_run.return_value = MagicMock(returncode=1, stderr="something broke")
        with pytest.raises(TerraformError, match="terraform plan failed"):
            orchestrator._run(["plan"], capture=True)

    @patch("overtime.terraform.base.subprocess.run")
    def test_nonzero_with_check_false_returns_result(self, mock_run, orchestrator):
        """Non-zero exit code with check=False does not raise."""
        mock_run.return_value = MagicMock(returncode=1)
        result = orchestrator._run(["workspace", "select", "foo"], check=False)
        assert result.returncode == 1


# ---------------------------------------------------------------------------
# TestVarArgs — -var flag generation
# ---------------------------------------------------------------------------


class TestVarArgs:
    """_var_args() generates ``-var key=value`` flags from _tf_vars."""

    def test_empty_by_default(self, orchestrator):
        """_var_args() returns an empty list when no TF vars are set."""
        assert orchestrator._var_args() == []

    def test_returns_var_flags(self, orchestrator):
        """_var_args() returns ``-var key=value`` for each registered variable."""
        orchestrator._tf_vars["ci_password"] = "secret123"
        result = orchestrator._var_args()
        assert result == ["-var", "ci_password=secret123"]

    def test_multiple_vars(self, orchestrator):
        """_var_args() handles multiple variables."""
        orchestrator._tf_vars["admin_password"] = "pw1"
        orchestrator._tf_vars["ci_password"] = "pw2"
        result = orchestrator._var_args()
        assert "-var" in result
        assert "admin_password=pw1" in result
        assert "ci_password=pw2" in result
        assert len(result) == 4  # two -var pairs


# ---------------------------------------------------------------------------
# TestLoadVmDefinitions — HCL parsing
# ---------------------------------------------------------------------------


class TestLoadVmDefinitions:
    """_load_vm_definitions() HCL parsing and error cases."""

    def test_parses_known_scenario(self, orchestrator):
        """Correctly parses vm_definitions for a known scenario."""
        vms = orchestrator._load_vm_definitions("ad-lab-m")
        assert len(vms) == 2
        assert {vm["name_suffix"] for vm in vms} == {"ad-1a", "ad-2a"}

    def test_parses_jumphost_scenario(self, orchestrator):
        """Correctly parses vm_definitions for a single-VM scenario."""
        vms = orchestrator._load_vm_definitions("jumphost")
        assert len(vms) == 1
        assert vms[0]["name_suffix"] == "lutil-1a"

    def test_missing_scenario_raises(self, orchestrator):
        """Requesting a scenario not in the HCL raises TerraformError."""
        with pytest.raises(TerraformError, match="No VM definitions"):
            orchestrator._load_vm_definitions("nonexistent")

    def test_missing_main_tf_raises(self, tmp_path):
        """Missing main.tf raises TerraformError."""
        orch = _StubOrchestrator(terraform_dir=tmp_path / "empty")
        with pytest.raises(TerraformError, match="main.tf not found"):
            orch._load_vm_definitions("ad-lab-m")

    def test_empty_vm_definitions_raises(self, tmp_path):
        """main.tf with no vm_definitions local raises TerraformError."""
        (tmp_path / "main.tf").write_text('locals { foo = "bar" }')
        orch = _StubOrchestrator(terraform_dir=tmp_path)
        with pytest.raises(TerraformError, match="vm_definitions not found"):
            orch._load_vm_definitions("ad-lab-m")


# ---------------------------------------------------------------------------
# TestInit — terraform init
# ---------------------------------------------------------------------------


class TestInit:
    """init() invokes terraform init."""

    def test_calls_terraform_init(self, orchestrator):
        """init() invokes ``terraform init -input=false``."""
        with patch.object(orchestrator, "_run") as mock_run:
            orchestrator.init()
        mock_run.assert_called_once_with(["init", "-input=false"])


# ---------------------------------------------------------------------------
# TestReadOutputs — terraform output -json
# ---------------------------------------------------------------------------


class TestReadOutputs:
    """read_outputs() parses terraform output."""

    def test_returns_terraform_outputs(self, orchestrator):
        """read_outputs() returns a TerraformOutputs instance."""
        json_str = json.dumps({
            "jumphost_ip_address": {"value": "10.0.0.5/24"},
        })
        with patch.object(
            orchestrator, "_run",
            return_value=MagicMock(stdout=json_str),
        ):
            outputs = orchestrator.read_outputs()

        assert isinstance(outputs, TerraformOutputs)
        assert outputs.jumphost_ip == "10.0.0.5/24"


# ---------------------------------------------------------------------------
# TestEnsureWorkspace — workspace select-or-create
# ---------------------------------------------------------------------------


class TestEnsureWorkspace:
    """ensure_workspace() tries select, falls back to new."""

    def test_selects_existing_workspace(self, orchestrator):
        """When workspace select succeeds, no new is issued."""
        with patch.object(orchestrator, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            orchestrator.ensure_workspace("lab", "ad-lab-m")

        mock_run.assert_called_once_with(
            ["workspace", "select", "env-lab-ad-lab-m"],
            check=False, capture=True,
        )

    def test_creates_on_select_failure(self, orchestrator):
        """When workspace select fails, workspace new is called."""
        with patch.object(orchestrator, "_run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1),  # select fails
                MagicMock(returncode=0),  # new succeeds
            ]
            orchestrator.ensure_workspace("lab", "k8s-dev")

        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["workspace", "select", "env-lab-k8s-dev"],
            check=False, capture=True,
        )
        mock_run.assert_any_call(["workspace", "new", "env-lab-k8s-dev"])
