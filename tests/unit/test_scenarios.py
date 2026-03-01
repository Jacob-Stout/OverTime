"""Tests for the scenario template library and provider-scenario lookup."""

import json
import pytest
from pathlib import Path

from click.testing import CliRunner

from overtime.scenarios import (
    PROVIDER_SCENARIOS,
    PROXMOX_SCENARIOS,
    AZURE_SCENARIOS,
    ScenarioTemplate,
    get_scenarios_for_provider,
    default_playbooks_for,
)
from overtime.config.schema import ProvisioningSpec, VmSpec
from overtime.cli import cli
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Registry lookup tests
# ---------------------------------------------------------------------------

class TestScenarioLookup:

    def test_get_scenarios_for_proxmox(self):
        result = get_scenarios_for_provider("proxmox")
        assert "ad-lab-m" in result
        assert "jumphost" in result

    def test_get_scenarios_for_azure(self):
        result = get_scenarios_for_provider("azure")
        assert "ad-lab-m" in result
        assert "jumphost" in result

    def test_unknown_provider_raises(self):
        with pytest.raises(KeyError):
            get_scenarios_for_provider("gcp")

    def test_all_entries_are_scenario_template(self):
        for provider, scenarios in PROVIDER_SCENARIOS.items():
            for name, info in scenarios.items():
                assert isinstance(info, ScenarioTemplate), f"{provider}/{name}"

    def test_scenario_template_has_vms_list(self):
        template = PROXMOX_SCENARIOS["ad-lab-m"]
        assert isinstance(template.vms, list)
        assert len(template.vms) > 0
        assert "name" in template.vms[0]
        assert "os" in template.vms[0]

    def test_scenario_template_vm_summary(self):
        template = PROXMOX_SCENARIOS["ad-lab-m"]
        summary = template.vm_summary
        assert "5 VMs" in summary
        assert "Windows" in summary

    def test_default_playbooks_for_ad_lab_m(self):
        pbs = default_playbooks_for("proxmox", "ad-lab-m")
        names = [p["playbook"] for p in pbs]
        assert "primary_ad_setup.yml" in names
        assert "secondary_ad_setup.yml" in names

    def test_default_playbooks_for_ad_lab_xs_no_secondary(self):
        pbs = default_playbooks_for("proxmox", "ad-lab-xs")
        names = [p["playbook"] for p in pbs]
        assert "primary_ad_setup.yml" in names
        assert "secondary_ad_setup.yml" not in names

    def test_default_playbooks_for_k8s_dev(self):
        pbs = default_playbooks_for("proxmox", "k8s-dev")
        assert len(pbs) == 1
        assert pbs[0]["playbook"] == "k8s_cluster_setup.yml"

    def test_default_playbooks_for_jumphost_has_setup_jumphost(self):
        pbs = default_playbooks_for("proxmox", "jumphost")
        assert len(pbs) == 1
        assert pbs[0]["playbook"] == "setup_jumphost.yml"
        assert pbs[0]["targets"] == "lutil"

    def test_default_playbooks_for_unknown_scenario(self):
        assert default_playbooks_for("proxmox", "nonexistent") == []

    def test_default_playbooks_for_unknown_provider(self):
        assert default_playbooks_for("gcp", "ad-lab-m") == []


# ---------------------------------------------------------------------------
# Schema validation tests (VmSpec, unique names, unique ip_offsets)
# ---------------------------------------------------------------------------

def _proxmox_spec_data(vms=None):
    if vms is None:
        vms = [
            {"name": "ad-1a", "os": "windows", "role": "ad", "ip_offset": 10},
        ]
    return {
        "provider": "proxmox",
        "proxmox": {
            "pm_api_url": "https://192.168.0.100:8006",
            "pm_user": "root@pam",
            "pm_password": "secret",
            "node_name": "pve",
            "storage_pool": "local-lvm",
            "network_bridge": "vmbr0",
            "linux_template_id": "222",
            "windows_template_id": "213",
            "subnet_cidr": "192.168.0.0/24",
            "vm_gateway": "192.168.0.1",
        },
        "environment": {
            "environment_name_prefix": "lab",
            "environment_fqdn": "lab.local",
            "workspace": "lab-ad-lab-m",
        },
        "ansible": {
            "ansible_user": "admin",
            "ansible_password": "secret",
            "ssh_pub_key": "ssh-ed25519 AAAA test@host",
        },
        "vms": vms,
    }


def _azure_spec_data(vms=None):
    if vms is None:
        vms = [
            {"name": "ad-1a", "os": "windows", "role": "ad", "ip_offset": 10},
        ]
    return {
        "provider": "azure",
        "azure": {
            "subscription_id": "12345678-1234-1234-1234-123456789abc",
            "resource_group": "rg",
            "location": "eastus",
            "vnet_name": "vnet",
            "vnet_cidr": "10.0.0.0/16",
            "subnet_cidr": "10.0.1.0/24",
        },
        "environment": {
            "environment_name_prefix": "lab",
            "environment_fqdn": "lab.local",
            "workspace": "lab-ad-lab-m",
        },
        "ansible": {
            "ansible_user": "overtimeadmin",
            "ansible_password": "secret",
            "ssh_pub_key": "ssh-ed25519 AAAA test@host",
            "ssh_key": "~/.ssh/id_ed25519",
        },
        "vms": vms,
    }


def _proxmox_token_spec_data(vms=None):
    """Like _proxmox_spec_data but uses pm_api_token instead of pm_password."""
    data = _proxmox_spec_data(vms)
    del data["proxmox"]["pm_password"]
    data["proxmox"]["pm_user"] = "overtime@pve!ot-token"
    data["proxmox"]["pm_api_token"] = "aabbccdd-1234-5678-9012-abcdef123456"
    return data


class TestProvisioningSpecVmValidation:

    def test_valid_proxmox_spec_with_vms(self):
        vms = [
            {"name": "ad-1a", "os": "windows", "role": "ad", "ip_offset": 10},
            {"name": "lutil-1a", "os": "linux", "role": "lutil", "ip_offset": 15},
        ]
        spec = ProvisioningSpec.model_validate(_proxmox_spec_data(vms))
        assert len(spec.vms) == 2
        assert spec.vms[0].name == "ad-1a"
        assert spec.vms[0].os == "windows"

    def test_duplicate_vm_names_rejected(self):
        vms = [
            {"name": "ad-1a", "os": "windows", "role": "ad", "ip_offset": 10},
            {"name": "ad-1a", "os": "windows", "role": "ad", "ip_offset": 11},
        ]
        with pytest.raises(ValidationError, match="Duplicate VM names"):
            ProvisioningSpec.model_validate(_proxmox_spec_data(vms))

    def test_duplicate_ip_offsets_rejected(self):
        vms = [
            {"name": "ad-1a", "os": "windows", "role": "ad", "ip_offset": 10},
            {"name": "ad-2a", "os": "windows", "role": "ad", "ip_offset": 10},
        ]
        with pytest.raises(ValidationError, match="Duplicate ip_offset"):
            ProvisioningSpec.model_validate(_proxmox_spec_data(vms))

    def test_empty_vms_rejected(self):
        with pytest.raises(ValidationError):
            ProvisioningSpec.model_validate(_proxmox_spec_data(vms=[]))

    def test_valid_proxmox_with_api_token(self):
        spec = ProvisioningSpec.model_validate(_proxmox_token_spec_data())
        assert spec.proxmox.pm_api_token is not None
        assert spec.proxmox.pm_password is None

    def test_proxmox_both_password_and_token_rejected(self):
        data = _proxmox_spec_data()
        data["proxmox"]["pm_api_token"] = "some-token"
        with pytest.raises(ValidationError, match="pm_password or pm_api_token, not both"):
            ProvisioningSpec.model_validate(data)

    def test_proxmox_neither_password_nor_token_rejected(self):
        data = _proxmox_spec_data()
        del data["proxmox"]["pm_password"]
        with pytest.raises(ValidationError, match="pm_password or pm_api_token is required"):
            ProvisioningSpec.model_validate(data)

    def test_vmspec_defaults(self):
        vm = VmSpec(name="ad-1a", os="windows", role="ad", ip_offset=10)
        assert vm.cpu == 2
        assert vm.memory is None
        assert vm.disk == 40


# ---------------------------------------------------------------------------
# CLI scenarios command tests
# ---------------------------------------------------------------------------

class TestScenariosCommand:

    def test_scenarios_lists_all_providers(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scenarios"])
        assert result.exit_code == 0
        assert "proxmox" in result.output
        assert "azure" in result.output

    def test_scenarios_filter_by_provider(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scenarios", "-p", "azure"])
        assert result.exit_code == 0
        assert "azure" in result.output
        assert "proxmox" not in result.output

    def test_scenarios_shows_descriptions(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scenarios", "-p", "proxmox"])
        assert "Active Directory lab (medium)" in result.output
        assert "5 VMs" in result.output

    def test_scenarios_shows_playbooks(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scenarios", "-p", "proxmox"])
        assert "primary_ad_setup.yml" in result.output

    def test_scenarios_json_output(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scenarios", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "proxmox" in data
        assert "azure" in data
        assert "ad-lab-m" in data["proxmox"]

    def test_scenarios_json_filtered(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scenarios", "-p", "azure", "--json"])
        data = json.loads(result.output)
        assert "azure" in data
        assert "proxmox" not in data
