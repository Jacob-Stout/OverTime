"""Tests for AzureNetworkOrchestrator."""

import json
from unittest.mock import patch, MagicMock

import pytest

from overtime.terraform.azure_network_orchestrator import AzureNetworkOrchestrator
from overtime.utils.exceptions import TerraformError


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def network_config() -> dict:
    """Minimal resolved config dict for Azure network operations."""
    return {
        "provider": "azure",
        "azure": {
            "subscription_id":   "12345678-1234-1234-1234-123456789abc",
            "resource_group":    "ot-lab-rg",
            "location":          "eastus",
            "vnet_name":         "ot-vnet",
            "vnet_cidr":         "10.0.0.0/16",
            "subnet_cidr":       "10.0.1.0/24",
            "default_vm_size":   "Standard_B2s",
            "admin_username":    "overtimeadmin",
            "allowed_source_prefix": "*",
        },
        "environment": {
            "environment_name_prefix": "lab",
            "environment_fqdn":        "lab.local",
            "workspace":               "lab-ad-lab-m",
        },
        "ansible": {
            "ansible_user":     "overtimeadmin",
            "ansible_password": "ansible_secret",
            "ssh_pub_key":      "ssh-ed25519 AAAA test@host",
        },
        "vms": [
            {"name": "ad-1a", "os": "windows", "role": "ad", "ip_offset": 10},
        ],
    }


# ---------------------------------------------------------------------------
# TestAzureNetworkOrchestrator — 9 tests
# ---------------------------------------------------------------------------


class TestAzureNetworkOrchestrator:
    """AzureNetworkOrchestrator with mocked subprocess and file I/O."""

    @pytest.fixture()
    def orchestrator(self, tmp_path) -> AzureNetworkOrchestrator:
        """Network orchestrator pointed at a temp directory."""
        return AzureNetworkOrchestrator(terraform_dir=tmp_path)

    # -- Constructor --------------------------------------------------------

    def test_default_terraform_dir(self):
        """Default terraform_dir resolves to terraform/azure-network."""
        orch = AzureNetworkOrchestrator()
        assert orch.terraform_dir.name == "azure-network"
        assert orch.terraform_dir.parent.name == "terraform"

    # -- Workspace management -----------------------------------------------

    def test_ensure_network_workspace_selects_existing(self, orchestrator):
        """If workspace exists, select it without creating a new one."""
        success = MagicMock(returncode=0)
        with patch.object(orchestrator, "_run", return_value=success) as mock_run:
            orchestrator.ensure_network_workspace("lab")

        mock_run.assert_called_once_with(
            ["workspace", "select", "net-lab"],
            check=False,
            capture=True,
        )

    def test_ensure_network_workspace_creates_new(self, orchestrator):
        """If workspace does not exist, create it after failed select."""
        failed = MagicMock(returncode=1)
        success = MagicMock(returncode=0)

        with patch.object(
            orchestrator, "_run", side_effect=[failed, success]
        ) as mock_run:
            orchestrator.ensure_network_workspace("azlab")

        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["workspace", "select", "net-azlab"],
            check=False,
            capture=True,
        )
        mock_run.assert_any_call(["workspace", "new", "net-azlab"])

    # -- Tfvars writing -----------------------------------------------------

    def test_write_tfvars_produces_valid_json(
        self, orchestrator, network_config
    ):
        """_write_tfvars writes parseable JSON with expected keys."""
        orchestrator._write_tfvars(network_config)
        tfvars_path = orchestrator.terraform_dir / "terraform.tfvars.json"
        tfvars = json.loads(tfvars_path.read_text())

        assert tfvars["subscription_id"] == "12345678-1234-1234-1234-123456789abc"
        assert tfvars["resource_group_name"] == "ot-lab-rg"
        assert tfvars["location"] == "eastus"
        assert tfvars["vnet_name"] == "ot-vnet"
        assert tfvars["vnet_cidr"] == "10.0.0.0/16"
        assert tfvars["environment_name_prefix"] == "lab"

    def test_write_tfvars_excludes_passwords(
        self, orchestrator, network_config
    ):
        """No password fields should appear in the network tfvars."""
        orchestrator._write_tfvars(network_config)
        tfvars = json.loads(
            (orchestrator.terraform_dir / "terraform.tfvars.json").read_text()
        )

        assert "admin_password" not in tfvars
        assert "ansible_password" not in tfvars

    # -- Environment setup --------------------------------------------------

    def test_set_env_sets_subscription_id(self, orchestrator, network_config):
        """_set_env registers ARM_SUBSCRIPTION_ID in _extra_env."""
        orchestrator._set_env(network_config)

        assert orchestrator._extra_env["ARM_SUBSCRIPTION_ID"] == "12345678-1234-1234-1234-123456789abc"

    # -- Lifecycle methods --------------------------------------------------

    def test_plan_calls_correct_sequence(self, orchestrator, network_config):
        """plan() sets env, writes tfvars, selects workspace, runs plan."""
        with (
            patch.object(orchestrator, "_set_env") as mock_env,
            patch.object(orchestrator, "_write_tfvars") as mock_tfvars,
            patch.object(orchestrator, "ensure_network_workspace") as mock_ws,
            patch.object(orchestrator, "_run") as mock_run,
        ):
            orchestrator.plan(network_config)

        mock_env.assert_called_once_with(network_config)
        mock_tfvars.assert_called_once_with(network_config)
        mock_ws.assert_called_once_with("lab")
        mock_run.assert_called_once_with(["plan", "-input=false"])

    def test_apply_passes_auto_approve(self, orchestrator, network_config):
        """apply(auto_approve=True) appends -auto-approve to terraform call."""
        with (
            patch.object(orchestrator, "_set_env"),
            patch.object(orchestrator, "_write_tfvars"),
            patch.object(orchestrator, "ensure_network_workspace"),
            patch.object(orchestrator, "_run") as mock_run,
            patch.object(orchestrator, "read_outputs", return_value=MagicMock()),
        ):
            orchestrator.apply(network_config, auto_approve=True)

        mock_run.assert_called_once_with(["apply", "-input=false", "-auto-approve"])

    def test_destroy_selects_workspace_and_destroys(
        self, orchestrator, network_config
    ):
        """destroy() sets env, selects workspace, and runs terraform destroy."""
        with (
            patch.object(orchestrator, "_set_env"),
            patch.object(orchestrator, "_write_tfvars"),
            patch.object(orchestrator, "ensure_network_workspace") as mock_ws,
            patch.object(orchestrator, "_run") as mock_run,
        ):
            orchestrator.destroy(network_config, auto_approve=True)

        mock_ws.assert_called_once_with("lab")
        mock_run.assert_called_once_with(["destroy", "-input=false", "-auto-approve"])
