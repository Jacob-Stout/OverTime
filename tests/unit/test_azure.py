"""Tests for Azure orchestrator and schema."""

import json
from unittest.mock import patch, MagicMock

import pytest
from pydantic import ValidationError

from overtime.terraform.azure_orchestrator import AzureOrchestrator
from overtime.config.schema import AzureConfig, ProvisioningSpec
from overtime.utils.exceptions import TerraformError


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# VM definition sets mirroring the Azure main.tf topologies.
# vm_size is omitted — var.default_vm_size serves as fallback in Terraform.

M_VM_DEFS = [
    {"name_suffix": "ad-1a",    "role": "ad",      "os_type": "windows", "ip_offset": 10, "disk_gb": 40},
    {"name_suffix": "ad-2a",    "role": "ad",      "os_type": "windows", "ip_offset": 11, "disk_gb": 40},
    {"name_suffix": "wutil-1a", "role": "wutil",   "os_type": "windows", "ip_offset": 12, "disk_gb": 40},
    {"name_suffix": "gen-1a",   "role": "general", "os_type": "windows", "ip_offset": 13, "disk_gb": 40},
    {"name_suffix": "gen-1b",   "role": "general", "os_type": "windows", "ip_offset": 14, "disk_gb": 40},
]

CTRL_VM_DEFS = [
    {"name_suffix": "lutil-1a", "role": "lutil", "os_type": "linux", "ip_offset": 10, "disk_gb": 30},
]


@pytest.fixture()
def azure_config() -> dict:
    """Minimal resolved config dict for an Azure M environment."""
    return {
        "provider": "azure",
        "azure": {
            "subscription_id":  "12345678-1234-1234-1234-123456789abc",
            "resource_group":   "ot-lab-M",
            "location":         "eastus",
            "vnet_name":        "ot-vnet",
            "vnet_cidr":        "10.0.0.0/16",
            "subnet_cidr":      "10.0.1.0/24",
            "default_vm_size":  "Standard_B2s",
            "admin_username":   "overtimeadmin",
            "allowed_source_prefix": "*",
        },
        "environment": {
            "scenario":                "ad-lab-m",
            "environment_name_prefix": "lab",
            "environment_fqdn":        "lab.local",
        },
        "ansible": {
            "ansible_user":     "overtimeadmin",
            "ansible_password": "ansible_secret",
            "ssh_pub_key":      "ssh-ed25519 AAAA test@host",
        },
    }


# ---------------------------------------------------------------------------
# TestAzureOrchestrator
# ---------------------------------------------------------------------------


class TestAzureOrchestrator:
    """Orchestrator internals with mocked subprocess and file I/O."""

    @pytest.fixture()
    def orchestrator(self, tmp_path) -> AzureOrchestrator:
        """Orchestrator pointed at tmp; main.tf fixture has M and jumphost sizes."""
        # Minimal HCL that python-hcl2 can parse — only the vm_definitions local.
        # vm_size is omitted (var.default_vm_size serves as fallback in Terraform).
        (tmp_path / "main.tf").write_text("""\
locals {
  vm_definitions = {
    "ad-lab-m" = [
      { name_suffix = "ad-1a",    role = "ad",      os_type = "windows", ip_offset = 10, disk_gb = 40 },
      { name_suffix = "ad-2a",    role = "ad",      os_type = "windows", ip_offset = 11, disk_gb = 40 },
      { name_suffix = "wutil-1a", role = "wutil",   os_type = "windows", ip_offset = 12, disk_gb = 40 },
      { name_suffix = "gen-1a",   role = "general", os_type = "windows", ip_offset = 13, disk_gb = 40 },
      { name_suffix = "gen-1b",   role = "general", os_type = "windows", ip_offset = 14, disk_gb = 40 },
    ]

    "jumphost" = [
      { name_suffix = "lutil-1a", role = "lutil", os_type = "linux", ip_offset = 10, disk_gb = 30 },
    ]
  }
}
""")
        return AzureOrchestrator(terraform_dir=tmp_path)

    # -- VM definition loading ----------------------------------------------

    def test_load_vm_definitions_parses_m_size(self, orchestrator):
        """_load_vm_definitions('ad-lab-m') returns 5 VM dicts from the fixture."""
        vms = orchestrator._load_vm_definitions("ad-lab-m")
        assert len(vms) == 5
        suffixes = {vm["name_suffix"] for vm in vms}
        assert suffixes == {"ad-1a", "ad-2a", "wutil-1a", "gen-1a", "gen-1b"}

    def test_load_vm_definitions_raises_for_missing_size(self, orchestrator):
        """Requesting a size not in the fixture raises TerraformError."""
        with pytest.raises(TerraformError, match="No VM definitions"):
            orchestrator._load_vm_definitions("ad-lab-xs")

    # -- Tfvars writing ----------------------------------------------------

    def test_write_tfvars_produces_valid_json(self, orchestrator, azure_config, tmp_path):
        """_write_tfvars writes parseable JSON to terraform.tfvars.json."""
        orchestrator._write_tfvars(azure_config)
        tfvars_path = orchestrator.terraform_dir / "terraform.tfvars.json"
        tfvars = json.loads(tfvars_path.read_text())

        assert tfvars["subscription_id"] == "12345678-1234-1234-1234-123456789abc"
        assert tfvars["resource_group_name"] == "ot-lab-M"
        assert tfvars["environment_name_prefix"] == "lab"
        assert "location" not in tfvars
        assert tfvars["scenario"] == "ad-lab-m"
        assert "init_configs" not in tfvars

    def test_write_tfvars_excludes_admin_password(
        self, orchestrator, azure_config, tmp_path
    ):
        """admin_password must never appear in the written tfvars file."""
        orchestrator._write_tfvars(azure_config)
        tfvars = json.loads(
            (orchestrator.terraform_dir / "terraform.tfvars.json").read_text()
        )

        assert "admin_password" not in tfvars
        assert "ansible_password" not in tfvars

    def test_write_tfvars_includes_default_vm_size(
        self, orchestrator, azure_config, tmp_path
    ):
        """_write_tfvars writes default_vm_size to tfvars."""
        orchestrator._write_tfvars(azure_config)
        tfvars = json.loads(
            (orchestrator.terraform_dir / "terraform.tfvars.json").read_text()
        )
        assert tfvars["default_vm_size"] == "Standard_B2s"

    def test_write_tfvars_includes_allowed_source_prefix(
        self, orchestrator, azure_config, tmp_path
    ):
        """_write_tfvars passes allowed_source_prefix through."""
        azure_config["azure"]["allowed_source_prefix"] = "10.0.0.1/32"
        orchestrator._write_tfvars(azure_config)
        tfvars = json.loads(
            (orchestrator.terraform_dir / "terraform.tfvars.json").read_text()
        )
        assert tfvars["allowed_source_prefix"] == "10.0.0.1/32"

    # -- Environment setup -------------------------------------------------

    def test_set_env_sets_required_vars(self, orchestrator, azure_config):
        """_set_env registers admin_password as a -var arg."""
        orchestrator._set_env(azure_config)

        assert orchestrator._tf_vars["admin_password"] == "ansible_secret"

    # -- Lifecycle methods --------------------------------------------------
    # _run, init, ensure_workspace, read_outputs are tested in
    # test_base_orchestrator.py (inherited from BaseOrchestrator).

    def test_apply_passes_auto_approve(self, orchestrator, azure_config):
        """apply(auto_approve=True) appends -auto-approve to the terraform call."""
        with (
            patch.object(orchestrator, "_set_env"),
            patch.object(orchestrator, "_load_vm_definitions", return_value=M_VM_DEFS),
            patch.object(orchestrator, "_write_tfvars"),
            patch.object(orchestrator, "ensure_workspace"),
            patch.object(orchestrator, "_run") as mock_run,
            patch.object(orchestrator, "read_outputs", return_value=MagicMock()),
            patch.object(orchestrator, "_disable_windows_firewall"),
        ):
            orchestrator.apply(azure_config, auto_approve=True)

        mock_run.assert_called_once_with(["apply", "-input=false", "-auto-approve"])

    def test_apply_disables_firewall_on_windows_vms(self, orchestrator, azure_config):
        """apply() calls _disable_windows_firewall for Windows VMs after terraform apply."""
        with (
            patch.object(orchestrator, "_set_env"),
            patch.object(orchestrator, "_load_vm_definitions", return_value=M_VM_DEFS),
            patch.object(orchestrator, "_write_tfvars"),
            patch.object(orchestrator, "ensure_workspace"),
            patch.object(orchestrator, "_run"),
            patch.object(orchestrator, "read_outputs", return_value=MagicMock()),
            patch.object(orchestrator, "_disable_windows_firewall") as mock_fw,
        ):
            orchestrator.apply(azure_config, auto_approve=True)

        mock_fw.assert_called_once()
        windows_vms, rg, prefix = mock_fw.call_args[0]
        assert len(windows_vms) == 5
        assert all(vm["os_type"] == "windows" for vm in windows_vms)
        assert rg == "ot-lab-M"
        assert prefix == "lab"

    def test_apply_skips_firewall_for_linux_only(self, orchestrator, azure_config):
        """apply() does not call _disable_windows_firewall when all VMs are Linux."""
        azure_config["environment"]["scenario"] = "jumphost"
        with (
            patch.object(orchestrator, "_set_env"),
            patch.object(orchestrator, "_load_vm_definitions", return_value=CTRL_VM_DEFS),
            patch.object(orchestrator, "_write_tfvars"),
            patch.object(orchestrator, "ensure_workspace"),
            patch.object(orchestrator, "_run"),
            patch.object(orchestrator, "read_outputs", return_value=MagicMock()),
            patch.object(orchestrator, "_disable_windows_firewall") as mock_fw,
        ):
            orchestrator.apply(azure_config, auto_approve=True)

        mock_fw.assert_not_called()

    @patch("overtime.terraform.azure_orchestrator.shutil.which", return_value="/usr/bin/az")
    @patch("overtime.terraform.azure_orchestrator.subprocess.run")
    def test_disable_windows_firewall_invokes_az_cli(self, mock_subproc, mock_which, orchestrator):
        """_disable_windows_firewall calls az vm run-command for each Windows VM."""
        mock_subproc.return_value = MagicMock(returncode=0)
        vms = [
            {"name_suffix": "ad-1a", "os_type": "windows"},
            {"name_suffix": "wutil-1a", "os_type": "windows"},
        ]
        orchestrator._disable_windows_firewall(vms, "my-rg", "lab")

        assert mock_subproc.call_count == 2
        for call_args in mock_subproc.call_args_list:
            cmd = call_args[0][0]
            assert cmd[:4] == ["az", "vm", "run-command", "invoke"]
            assert "--resource-group" in cmd
            assert "my-rg" in cmd
            assert "Set-NetFirewallProfile" in cmd[-1]

    def test_destroy_selects_workspace_and_runs_destroy(self, orchestrator, azure_config):
        """destroy() sets env, selects workspace, and runs ``terraform destroy``."""
        with (
            patch.object(orchestrator, "_set_env"),
            patch.object(orchestrator, "ensure_workspace") as mock_ws,
            patch.object(orchestrator, "_run") as mock_run,
        ):
            orchestrator.destroy(azure_config, auto_approve=True)

        mock_ws.assert_called_once_with("lab", "ad-lab-m")
        mock_run.assert_called_once_with(["destroy", "-input=false", "-auto-approve"])

    def test_get_vm_definitions_delegates_to_loader(self, orchestrator, azure_config):
        """get_vm_definitions() is a thin wrapper over _load_vm_definitions."""
        with patch.object(
            orchestrator, "_load_vm_definitions", return_value=CTRL_VM_DEFS
        ) as mock_load:
            result = orchestrator.get_vm_definitions(azure_config)

        mock_load.assert_called_once_with("ad-lab-m")
        assert result is CTRL_VM_DEFS


# ---------------------------------------------------------------------------
# TestAzureSchema — 6 tests
# ---------------------------------------------------------------------------


class TestAzureSchema:
    """Pydantic validation for AzureConfig and ProvisioningSpec azure field."""

    def _valid_azure_data(self) -> dict:
        """Return a minimal valid AzureConfig payload."""
        return {
            "subscription_id": "12345678-1234-1234-1234-123456789abc",
            "resource_group": "ot-lab-M",
            "location": "eastus",
            "vnet_name": "ot-vnet",
            "vnet_cidr": "10.0.0.0/16",
            "subnet_cidr": "10.0.1.0/24",
        }

    def _valid_spec_data(self) -> dict:
        """Return a minimal valid ProvisioningSpec payload with provider=azure."""
        return {
            "provider": "azure",
            "azure": self._valid_azure_data(),
            "environment": {
                "environment_name_prefix": "lab",
                "scenario": "ad-lab-m",
                "environment_fqdn": "lab.local",
            },
            "ansible": {
                "ansible_user": "overtimeadmin",
                "ansible_password": "secret",
                "ssh_pub_key": "ssh-ed25519 AAAA test@host",
                "ssh_key": "~/.ssh/id_ed25519",
            },
        }

    def test_valid_azure_config_passes(self):
        """A fully populated AzureConfig validates without error."""
        cfg = AzureConfig.model_validate(self._valid_azure_data())
        assert cfg.subscription_id == "12345678-1234-1234-1234-123456789abc"
        assert cfg.default_vm_size == "Standard_B2s"        # default applied
        assert cfg.admin_username == "overtimeadmin"        # default applied

    def test_invalid_subscription_id_raises(self):
        """subscription_id that is not a UUID is rejected."""
        data = self._valid_azure_data()
        data["subscription_id"] = "not-a-uuid"
        with pytest.raises(ValidationError, match="subscription_id must be a valid UUID"):
            AzureConfig.model_validate(data)

    def test_reserved_admin_username_raises(self):
        """Reserved Azure usernames ('admin', 'root', etc.) are rejected."""
        data = self._valid_azure_data()
        data["admin_username"] = "admin"
        with pytest.raises(ValidationError, match="Azure rejects reserved username"):
            AzureConfig.model_validate(data)

    def test_provider_azure_without_azure_block_raises(self):
        """ProvisioningSpec with provider=azure but no azure block is invalid."""
        data = self._valid_spec_data()
        del data["azure"]
        with pytest.raises(ValidationError, match="Azure configuration required"):
            ProvisioningSpec.model_validate(data)

    def test_allowed_source_prefix_defaults_to_star(self):
        """allowed_source_prefix defaults to '*' when omitted."""
        cfg = AzureConfig.model_validate(self._valid_azure_data())
        assert cfg.allowed_source_prefix == "*"

    def test_allowed_source_prefix_accepts_cidr(self):
        """allowed_source_prefix accepts a CIDR string."""
        data = self._valid_azure_data()
        data["allowed_source_prefix"] = "203.0.113.5/32"
        cfg = AzureConfig.model_validate(data)
        assert cfg.allowed_source_prefix == "203.0.113.5/32"

    def test_empty_ansible_password_rejected(self):
        """An empty ansible_password is rejected by min_length=1."""
        data = self._valid_spec_data()
        data["ansible"]["ansible_password"] = ""
        with pytest.raises(ValidationError, match="ansible_password"):
            ProvisioningSpec.model_validate(data)

    def test_empty_ansible_user_rejected(self):
        """An empty ansible_user is rejected by min_length=1."""
        data = self._valid_spec_data()
        data["ansible"]["ansible_user"] = ""
        with pytest.raises(ValidationError, match="ansible_user"):
            ProvisioningSpec.model_validate(data)

    def test_azure_ssh_pub_key_without_ssh_key_rejected(self):
        """Azure with ssh_pub_key but no ssh_key is rejected."""
        data = self._valid_spec_data()
        del data["ansible"]["ssh_key"]
        with pytest.raises(ValidationError, match="ssh_key.*required"):
            ProvisioningSpec.model_validate(data)

    def test_azure_ssh_pub_key_with_ssh_key_passes(self):
        """Azure with both ssh_pub_key and ssh_key validates successfully."""
        data = self._valid_spec_data()
        data["ansible"]["ssh_pub_key"] = "ssh-ed25519 AAAA test@host"
        data["ansible"]["ssh_key"] = "~/.ssh/id_ed25519"
        spec = ProvisioningSpec.model_validate(data)
        assert spec.ansible.ssh_key == "~/.ssh/id_ed25519"

    def test_azure_no_ssh_pub_key_no_ssh_key_passes(self):
        """Azure with neither ssh_pub_key nor ssh_key validates (password auth)."""
        data = self._valid_spec_data()
        data["ansible"]["ssh_pub_key"] = ""
        del data["ansible"]["ssh_key"]
        spec = ProvisioningSpec.model_validate(data)
        assert spec.ansible.ssh_key is None
