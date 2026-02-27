"""Tests for Terraform state reader, orchestrator, and Ansible inventory generator."""

import json
from unittest.mock import patch, MagicMock

import pytest
import yaml

from overtime.terraform.state import TerraformOutputs
from overtime.terraform.pve_orchestrator import PveOrchestrator
from overtime.ansible.inventory import AnsibleInventoryGenerator, InventoryGenerationError
from overtime.utils.exceptions import TerraformError


# ---------------------------------------------------------------------------
# Shared fixtures and sample data
# ---------------------------------------------------------------------------


@pytest.fixture()
def tf_output_json() -> str:
    """Realistic ``terraform output -json`` payload for a jumphost environment."""
    return json.dumps({
        "jumphost_ip_address": {
            "value": "192.168.0.15/24",
            "type": "string",
            "sensitive": False,
        },
        "all_vm_ips": {
            "value": {"lab-lutil-1a": "192.168.0.15/24"},
            "type": ["object", {"lab-lutil-1a": "string"}],
            "sensitive": False,
        },
        "all_vm_ids": {
            "value": {"lab-lutil-1a": 9100},
            "type": ["object", {"lab-lutil-1a": "number"}],
            "sensitive": False,
        },
    })


@pytest.fixture()
def sample_config() -> dict:
    """Minimal resolved config dict for a jumphost environment."""
    return {
        "proxmox": {
            "pm_api_url":            "https://proxmox.local:8006",
            "pm_user":               "root@pam",
            "pm_password":           "super_secret",
            "pm_tls_insecure":       True,
            "node_name":             "pve01",
            "storage_pool":          "local-lvm",
            "network_bridge":        "vmbr2",
            "linux_template_id":     "222",
            "windows_template_id":   "213",
            "subnet_cidr":           "192.168.0.0/24",
            "vm_gateway":            "192.168.0.1",
        },
        "environment": {
            "scenario":                "jumphost",
            "environment_name_prefix": "lab",
            "environment_fqdn":        "lab.local",
        },
        "ansible": {
            "ansible_user":     "overtimeadmin",
            "ansible_password": "ansible_secret",
            "ssh_pub_key":      "ssh-ed25519 AAAA test@host",
        },
    }


# Module-level VM definition sets used by multiple test classes

CTRL_VM_DEFS = [
    {
        "name_suffix": "lutil-1a", "role": "lutil", "cpu": 2,
        "memory": 4096, "disk_size": "32G", "os_type": "cloud-init",
        "ip_offset": 15,
    },
]

DEV_VM_DEFS = [
    {
        "name_suffix": "k8s-1a", "role": "ctrl", "cpu": 2, "memory": 4096,
        "disk_size": "32G", "os_type": "cloud-init", "ip_offset": 60,
    },
    {
        "name_suffix": "k8s-1b", "role": "ctrl", "cpu": 2, "memory": 4096,
        "disk_size": "32G", "os_type": "cloud-init", "ip_offset": 61,
    },
    {
        "name_suffix": "k8s-1d", "role": "work", "cpu": 4, "memory": 8192,
        "disk_size": "32G", "os_type": "cloud-init", "ip_offset": 63,
    },
]

XS_WINDOWS_VM_DEFS = [
    {
        "name_suffix": "ad-1a", "role": "ad", "cpu": 2, "memory": 4096,
        "disk_size": "40G", "os_type": "windows", "ip_offset": 10,
    },
    {
        "name_suffix": "wutil-1a", "role": "wutil", "cpu": 2, "memory": 4096,
        "disk_size": "40G", "os_type": "windows", "ip_offset": 20,
    },
    {
        "name_suffix": "gen-1a", "role": "general", "cpu": 2, "memory": 4096,
        "disk_size": "40G", "os_type": "windows", "ip_offset": 50,
    },
]


def _make_tf_outputs(ip_map: dict, id_map: dict = None, jumphost_ip: str = None) -> TerraformOutputs:
    """Build a TerraformOutputs from convenience maps."""
    raw = {"all_vm_ips": {"value": ip_map}}
    if id_map is not None:
        raw["all_vm_ids"] = {"value": id_map}
    if jumphost_ip is not None:
        raw["jumphost_ip_address"] = {"value": jumphost_ip}
    return TerraformOutputs(raw)


# ---------------------------------------------------------------------------
# TestTerraformOutputs — 6 tests
# ---------------------------------------------------------------------------


class TestTerraformOutputs:
    """Parsing and typed-property access for ``terraform output -json``."""

    def test_parses_valid_json(self, tf_output_json):
        """from_json constructs the object; get() returns None for missing keys."""
        outputs = TerraformOutputs.from_json(tf_output_json)
        assert isinstance(outputs, TerraformOutputs)
        assert outputs.get("does_not_exist") is None

    def test_jumphost_ip_when_present(self, tf_output_json):
        """jumphost_ip returns the IP string when the output exists."""
        outputs = TerraformOutputs.from_json(tf_output_json)
        assert outputs.jumphost_ip == "192.168.0.15/24"

    def test_jumphost_ip_when_absent(self):
        """jumphost_ip is None when the output is missing from state."""
        outputs = TerraformOutputs.from_json(json.dumps({}))
        assert outputs.jumphost_ip is None

    def test_wutil_ip_when_present(self):
        """wutil_ip returns the IP string when the output exists."""
        raw = json.dumps({"wutil_ip_address": {"value": "20.1.2.3"}})
        outputs = TerraformOutputs.from_json(raw)
        assert outputs.wutil_ip == "20.1.2.3"

    def test_wutil_ip_when_absent(self):
        """wutil_ip is None when the output is missing from state."""
        outputs = TerraformOutputs.from_json(json.dumps({}))
        assert outputs.wutil_ip is None

    def test_all_vm_ips_returns_full_map(self, tf_output_json):
        """all_vm_ips returns every name→IP pair from the output."""
        outputs = TerraformOutputs.from_json(tf_output_json)
        assert outputs.all_vm_ips == {"lab-lutil-1a": "192.168.0.15/24"}

    def test_all_vm_ids_returns_full_map(self, tf_output_json):
        """all_vm_ids returns every name→VMID pair from the output."""
        outputs = TerraformOutputs.from_json(tf_output_json)
        assert outputs.all_vm_ids == {"lab-lutil-1a": 9100}

    def test_invalid_json_raises_terraform_error(self):
        """Both malformed JSON and non-object JSON raise TerraformError."""
        with pytest.raises(TerraformError, match="Failed to parse"):
            TerraformOutputs.from_json("not json at all")

        with pytest.raises(TerraformError, match="must be an object"):
            TerraformOutputs.from_json('"just a string"')


# ---------------------------------------------------------------------------
# TestPveOrchestrator — 8 tests
# ---------------------------------------------------------------------------


class TestPveOrchestrator:
    """Lifecycle methods with mocked subprocess and file I/O."""

    @pytest.fixture()
    def orchestrator(self, tmp_path) -> PveOrchestrator:
        """Orchestrator pointed at a temp directory; no real Terraform needed."""
        (tmp_path / "main.tf").write_text("")  # placeholder
        return PveOrchestrator(terraform_dir=tmp_path)

    # -- init & workspace --------------------------------------------------

    def test_init_calls_terraform_init(self, orchestrator):
        """init() invokes ``terraform init -input=false``."""
        with patch.object(orchestrator, "_run") as mock_run:
            orchestrator.init()
        mock_run.assert_called_once_with(["init", "-input=false"])

    def test_ensure_workspace_selects_existing(self, orchestrator):
        """When the workspace exists the select succeeds and no new is issued."""
        with patch.object(orchestrator, "_run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            orchestrator.ensure_workspace("lab", "ctrl")
        mock_run.assert_called_once_with(
            ["workspace", "select", "env-lab-ctrl"], check=False, capture=True,
        )

    def test_ensure_workspace_creates_on_miss(self, orchestrator):
        """When select fails, ``workspace new`` is called."""
        with patch.object(orchestrator, "_run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1),  # select → not found
                MagicMock(returncode=0),  # new    → ok
            ]
            orchestrator.ensure_workspace("lab", "dev")

        assert mock_run.call_count == 2
        mock_run.assert_any_call(
            ["workspace", "select", "env-lab-dev"], check=False, capture=True,
        )
        mock_run.assert_any_call(["workspace", "new", "env-lab-dev"])

    # -- tfvars writing ----------------------------------------------------

    def test_write_tfvars_excludes_sensitive_fields(self, orchestrator, tmp_path, sample_config):
        """pm_password, pm_api_token, and ansible_password are not written to tfvars.json."""
        orchestrator._write_tfvars(sample_config)
        tfvars = json.loads((tmp_path / "terraform.tfvars.json").read_text())

        assert "pm_password" not in tfvars
        assert "pm_api_token" not in tfvars
        assert "ansible_password" not in tfvars

    def test_write_tfvars_includes_dns_servers(self, orchestrator, tmp_path, sample_config):
        """dns_servers list appears in tfvars.json."""
        orchestrator._write_tfvars(sample_config)
        tfvars = json.loads((tmp_path / "terraform.tfvars.json").read_text())

        assert tfvars["dns_servers"] == ["192.168.0.1", "8.8.8.8"]

    # -- plan & apply ------------------------------------------------------

    def test_plan_invokes_workspace_then_plan(self, orchestrator, sample_config):
        """plan() selects the workspace and runs ``terraform plan``."""
        with (
            patch.object(orchestrator, "_write_tfvars"),
            patch.object(orchestrator, "ensure_workspace") as mock_ws,
            patch.object(orchestrator, "_run") as mock_run,
        ):
            orchestrator.plan(sample_config)

        mock_ws.assert_called_once_with("lab", "jumphost")
        mock_run.assert_called_once_with(["plan", "-input=false"])

    def test_apply_passes_auto_approve(self, orchestrator, sample_config, tf_output_json):
        """apply(auto_approve=True) appends -auto-approve to the terraform call."""
        with (
            patch.object(orchestrator, "_write_tfvars"),
            patch.object(orchestrator, "ensure_workspace"),
            patch.object(orchestrator, "_run") as mock_run,
            patch.object(orchestrator, "read_outputs",
                         return_value=TerraformOutputs.from_json(tf_output_json)),
        ):
            orchestrator.apply(sample_config, auto_approve=True)

        mock_run.assert_called_once_with(["apply", "-input=false", "-auto-approve"])


# ---------------------------------------------------------------------------
# TestAnsibleInventoryGenerator — 6 tests
# ---------------------------------------------------------------------------


class TestAnsibleInventoryGenerator:
    """Inventory structure, role grouping, and YAML serialization."""

    # -- helpers -----------------------------------------------------------

    def _windows_outputs(self) -> TerraformOutputs:
        return _make_tf_outputs(ip_map={
            "lab-ad-1a":   "192.168.0.10/24",
            "lab-wutil-1a": "192.168.0.20/24",
            "lab-gen-1a":  "192.168.0.50/24",
        })

    def _linux_outputs(self) -> TerraformOutputs:
        return _make_tf_outputs(
            ip_map={
                "lab-k8s-1a": "192.168.0.60/24",
                "lab-k8s-1b": "192.168.0.61/24",
                "lab-k8s-1d": "192.168.0.63/24",
            },
            jumphost_ip="192.168.0.60/24",
        )

    def _make_gen(self, outputs, vm_defs, **kwargs) -> AnsibleInventoryGenerator:
        defaults = dict(
            name_prefix="lab",
            fqdn="lab.local",
            ansible_user="overtimeadmin",
            ansible_password="secret",
        )
        defaults.update(kwargs)
        return AnsibleInventoryGenerator(outputs, vm_defs, **defaults)

    # -- tests -------------------------------------------------------------

    def test_generates_windows_inventory(self):
        """Windows environments include WinRM vars at the group level."""
        inv = self._make_gen(self._windows_outputs(), XS_WINDOWS_VM_DEFS).generate()

        # Connection vars are per-group, not global
        ad_group = inv["all"]["children"]["ad"]
        assert ad_group["vars"]["ansible_connection"] == "winrm"
        assert ad_group["vars"]["ansible_winrm_port"] == 5985
        assert ad_group["vars"]["ansible_winrm_server_cert_validation"] == "ignore"

        assert "lab-ad-1a" in ad_group["hosts"]
        assert ad_group["hosts"]["lab-ad-1a"] == {"ansible_host": "192.168.0.10"}

        # No connection vars at all level
        assert "ansible_connection" not in inv["all"]["vars"]

    def test_generates_linux_inventory(self):
        """Linux environments get ssh as the connection type at sub-group level."""
        inv = self._make_gen(self._linux_outputs(), DEV_VM_DEFS).generate()

        k8s_group = inv["all"]["children"]["k8s"]
        # k8s is now a parent with children, not a flat group
        assert "children" in k8s_group
        ctrl_vars = k8s_group["children"]["k8s_ctrl"]["vars"]
        assert ctrl_vars["ansible_connection"] == "ssh"
        assert "ansible_winrm_port" not in ctrl_vars
        assert "ansible_connection" not in inv["all"]["vars"]

    def test_ctrl_work_roles_grouped_under_k8s(self):
        """ctrl and work roles become k8s_ctrl/k8s_work sub-groups under k8s."""
        inv = self._make_gen(self._linux_outputs(), DEV_VM_DEFS).generate()

        k8s_group = inv["all"]["children"]["k8s"]
        assert "children" in k8s_group
        ctrl_hosts = k8s_group["children"]["k8s_ctrl"]["hosts"]
        work_hosts = k8s_group["children"]["k8s_work"]["hosts"]
        assert set(ctrl_hosts.keys()) == {"lab-k8s-1a", "lab-k8s-1b"}
        assert set(work_hosts.keys()) == {"lab-k8s-1d"}

    def test_k8s_subgroups_have_ssh_connection_vars(self):
        """Both k8s_ctrl and k8s_work sub-groups get ansible_connection: ssh."""
        inv = self._make_gen(self._linux_outputs(), DEV_VM_DEFS).generate()

        k8s_children = inv["all"]["children"]["k8s"]["children"]
        for subgroup in ("k8s_ctrl", "k8s_work"):
            assert k8s_children[subgroup]["vars"]["ansible_connection"] == "ssh"

    def test_non_k8s_scenarios_unaffected(self):
        """AD scenario inventory has flat groups — no children nesting."""
        inv = self._make_gen(self._windows_outputs(), XS_WINDOWS_VM_DEFS).generate()

        ad_group = inv["all"]["children"]["ad"]
        assert "hosts" in ad_group
        assert "children" not in ad_group

    def test_missing_vm_ip_raises_error(self):
        """A VM present in definitions but absent from outputs raises."""
        outputs = _make_tf_outputs(ip_map={
            "lab-ad-1a":   "192.168.0.10/24",
            "lab-wutil-1a": "192.168.0.20/24",
            # lab-gen-1a intentionally missing
        })
        with pytest.raises(InventoryGenerationError, match="lab-gen-1a"):
            self._make_gen(outputs, XS_WINDOWS_VM_DEFS).generate()

    def test_to_yaml_produces_parseable_yaml(self):
        """to_yaml() output round-trips through yaml.safe_load cleanly."""
        yaml_str = self._make_gen(self._windows_outputs(), XS_WINDOWS_VM_DEFS).to_yaml()
        parsed = yaml.safe_load(yaml_str)

        assert "all" in parsed
        assert "children" in parsed["all"]
        assert "ad" in parsed["all"]["children"]

    def test_ssh_key_path_added_to_all_vars(self):
        """ansible_ssh_private_key_file appears in all.vars when ssh_key_path is set."""
        inv = self._make_gen(
            self._linux_outputs(), DEV_VM_DEFS,
            ssh_key_path="~/.ssh/ot_key",
        ).generate()
        assert inv["all"]["vars"]["ansible_ssh_private_key_file"] == "~/.ssh/ot_key"

    def test_ssh_key_path_absent_by_default(self):
        """ansible_ssh_private_key_file is not set when ssh_key_path is omitted."""
        inv = self._make_gen(self._linux_outputs(), DEV_VM_DEFS).generate()
        assert "ansible_ssh_private_key_file" not in inv["all"]["vars"]

