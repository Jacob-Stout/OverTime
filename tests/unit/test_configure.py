"""Tests for probes, configure plan, remote runner, and setup wizard."""

from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

from overtime.utils.probes import (
    wait_for_port, wait_for_vm,
    ProbeTimeout, ProbeResult,
)
from overtime.ansible.configure_plan import PlaybookStep, build_configure_plan
from overtime.ansible.remote_runner import RemoteRunner
import yaml
from click.testing import CliRunner

from overtime.scenarios import default_playbooks_for
from overtime.cli import cli


# ===========================================================================
# TestReadinessProbes — 6 tests
# ===========================================================================


class TestReadinessProbes:
    """wait_for_port, wait_for_vm, wait_for_all_vms."""

    # ── wait_for_port ─────────────────────────────────────────────────

    @patch("overtime.utils.probes.socket.create_connection")
    def test_wait_for_port_returns_elapsed_on_success(self, mock_conn):
        """Successful TCP connect returns elapsed time > 0."""
        mock_conn.return_value.__enter__ = lambda s: s
        mock_conn.return_value.__exit__  = lambda s, *_: None

        elapsed = wait_for_port("127.0.0.1", 22, timeout=5, interval=1)
        assert elapsed >= 0.0
        mock_conn.assert_called_once_with(("127.0.0.1", 22), timeout=5)

    @patch("overtime.utils.probes.socket.create_connection")
    @patch("overtime.utils.probes.time.monotonic")
    @patch("overtime.utils.probes.time.sleep")
    def test_wait_for_port_raises_probe_timeout(self, mock_sleep, mock_mono, mock_conn):
        """ProbeTimeout raised when deadline passes without successful connect."""
        # monotonic: call 1 = start (100.0), call 2 = deadline check (106.0 > 105.0)
        mock_mono.side_effect = [100.0, 106.0]
        mock_conn.side_effect = ConnectionRefusedError

        with pytest.raises(ProbeTimeout, match="not reachable after 5s"):
            wait_for_port("10.0.0.1", 22, timeout=5, interval=1)

    # ── wait_for_vm ───────────────────────────────────────────────────

    @patch("overtime.utils.probes.wait_for_port", return_value=2.5)
    def test_wait_for_vm_strips_cidr(self, mock_port):
        """IP with CIDR suffix is stripped before probing."""
        result = wait_for_vm("vm1", "10.0.1.10/24", "linux", timeout=60)
        mock_port.assert_called_once_with("10.0.1.10", 22, timeout=60, interval=10)
        assert result.ip == "10.0.1.10"
        assert result.reachable is True

    @patch("overtime.utils.probes.wait_for_port", return_value=1.0)
    def test_wait_for_vm_port_selection(self, mock_port):
        """Port 22 for linux/cloud-init; 5985 for windows; 22 for unknown."""
        # linux
        wait_for_vm("v1", "1.1.1.1", "linux", timeout=10)
        assert mock_port.call_args_list[-1] == call("1.1.1.1", 22, timeout=10, interval=10)

        # cloud-init
        wait_for_vm("v2", "1.1.1.2", "cloud-init", timeout=10)
        assert mock_port.call_args_list[-1] == call("1.1.1.2", 22, timeout=10, interval=10)

        # windows
        wait_for_vm("v3", "1.1.1.3", "windows", timeout=10)
        assert mock_port.call_args_list[-1] == call("1.1.1.3", 5985, timeout=10, interval=10)

        # unknown → default 22
        wait_for_vm("v4", "1.1.1.4", "bsd", timeout=10)
        assert mock_port.call_args_list[-1] == call("1.1.1.4", 22, timeout=10, interval=10)

    @patch("overtime.utils.probes.wait_for_port", side_effect=ProbeTimeout("x"))
    def test_wait_for_vm_returns_unreachable_on_timeout(self, _):
        """wait_for_vm does NOT raise; returns reachable=False."""
        result = wait_for_vm("vm1", "10.0.0.1", "linux", timeout=5)
        assert result.reachable is False
        assert result.elapsed == 5.0



# ===========================================================================
# TestConfigurePlan — 7 tests
# ===========================================================================


# Shared VM definition sets

_JUMPHOST_DEFS = [
    {"role": "lutil", "name_suffix": "lutil-1a"},
]

_AD_LAB_M_DEFS = [
    {"role": "ad",       "name_suffix": "ad-1a"},
    {"role": "ad",       "name_suffix": "ad-2a"},
    {"role": "wutil",    "name_suffix": "wutil-1a"},
    {"role": "general",  "name_suffix": "gen-1a"},
    {"role": "general",  "name_suffix": "gen-1b"},
]

_K8S_DEV_DEFS = [
    {"role": "ctrl", "name_suffix": "k8s-1a"},
    {"role": "ctrl", "name_suffix": "k8s-1b"},
    {"role": "work", "name_suffix": "k8s-1d"},
]


class TestConfigurePlan:
    """build_configure_plan — system steps, user steps, edge cases."""

    def test_empty_manifest_only_system_steps(self):
        """No user playbooks → only probe_targets (no lutil in defs)."""
        plan = build_configure_plan(_K8S_DEV_DEFS, [])
        assert len(plan) == 1
        assert plan[0].playbook == "probe_targets.yml"

    def test_jumphost_absent_no_setup_step(self):
        """When lutil is not in topology, setup_jumphost is omitted."""
        plan = build_configure_plan(_AD_LAB_M_DEFS, [])
        playbooks = [s.playbook for s in plan]
        assert "setup_jumphost.yml" not in playbooks
        assert "probe_targets.yml" in playbooks

    def test_jumphost_present_setup_prepended(self):
        """When lutil is in topology, setup_jumphost.yml is first."""
        plan = build_configure_plan(_JUMPHOST_DEFS, [])
        assert plan[0].playbook == "setup_jumphost.yml"
        assert plan[0].targets  == "lutil"

    def test_jumphost_only_no_probe_targets(self):
        """When only lutil exists (jumphost), probe_targets is skipped."""
        plan = build_configure_plan(_JUMPHOST_DEFS, [])
        playbooks = [s.playbook for s in plan]
        assert "probe_targets.yml" not in playbooks

    def test_mixed_topology_includes_probe_targets(self):
        """When lutil + other VMs exist, both setup and probe steps appear."""
        mixed_defs = _JUMPHOST_DEFS + _AD_LAB_M_DEFS
        plan = build_configure_plan(mixed_defs, [])
        assert plan[0].playbook == "setup_jumphost.yml"
        assert plan[1].playbook == "probe_targets.yml"

    def test_manifest_entries_appear_in_order(self):
        """User playbooks appear after system steps, in spec order."""
        manifest = [
            {"playbook": "alpha.yml", "targets": "ad"},
            {"playbook": "beta.yml",  "targets": "general"},
        ]
        plan = build_configure_plan(_AD_LAB_M_DEFS, manifest)
        # system: probe_targets (no lutil)
        # user: alpha, beta
        assert plan[1].playbook == "alpha.yml"
        assert plan[2].playbook == "beta.yml"

    def test_setup_jumphost_has_no_extra_vars(self):
        """setup_jumphost step has empty extra_vars by default."""
        plan = build_configure_plan(_JUMPHOST_DEFS, [])
        assert plan[0].extra_vars == {}

    def test_custom_description_overrides_default(self):
        """A manifest entry with 'description' overrides the playbook filename."""
        manifest = [
            {"playbook": "foo.yml", "targets": "ad", "description": "My custom step"},
        ]
        plan = build_configure_plan(_AD_LAB_M_DEFS, manifest)
        user_step = plan[-1]
        assert user_step.description == "My custom step"

    def test_system_step_not_duplicated_when_in_manifest(self):
        """setup_jumphost.yml is not prepended if already in the manifest."""
        manifest = [
            {"playbook": "setup_jumphost.yml", "targets": "lutil"},
        ]
        plan = build_configure_plan(_JUMPHOST_DEFS, manifest)
        playbook_names = [s.playbook for s in plan]
        assert playbook_names.count("setup_jumphost.yml") == 1


# ===========================================================================
# TestRemoteRunner — 7 tests
# ===========================================================================


def _mock_client():
    """Return a MagicMock that behaves like a paramiko SSHClient."""
    client = MagicMock()
    # Default: exec_command returns exit 0 with empty output
    stdout_mock = MagicMock()
    stdout_mock.channel.recv_exit_status.return_value = 0
    stdout_mock.read.return_value = b""
    stderr_mock = MagicMock()
    stderr_mock.read.return_value = b""
    client.exec_command.return_value = (None, stdout_mock, stderr_mock)
    return client


class TestRemoteRunner:
    """Bootstrap, upload, step execution, plan halting."""

    def _runner(self) -> RemoteRunner:
        """Runner with a mocked SSHClient already connected."""
        runner = RemoteRunner("10.0.0.1", "admin", password="secret")
        runner._client = _mock_client()
        return runner

    # ── bootstrap_ansible ─────────────────────────────────────────────

    def test_bootstrap_ansible_skips_when_present(self):
        """If 'which ansible' exits 0, no install command is issued."""
        runner = self._runner()
        # which ansible → exit 0
        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 0
        runner._client.exec_command.return_value = (None, stdout, MagicMock())

        runner.bootstrap_ansible()

        # Only one exec_command call (the 'which' check)
        runner._client.exec_command.assert_called_once_with("which ansible")

    def test_bootstrap_ansible_runs_install_when_absent(self):
        """If 'which ansible' exits 1, the PPA install command is issued."""
        runner = self._runner()

        # First call: which ansible → exit 1
        which_stdout = MagicMock()
        which_stdout.channel.recv_exit_status.return_value = 1

        # Second call: install → exit 0
        install_stdout = MagicMock()
        install_stdout.channel.recv_exit_status.return_value = 0
        install_stderr = MagicMock()
        install_stderr.read.return_value = b""

        runner._client.exec_command.side_effect = [
            (None, which_stdout, MagicMock()),
            (None, install_stdout, install_stderr),
        ]

        runner.bootstrap_ansible()
        assert runner._client.exec_command.call_count == 2
        # Second call should contain the install command
        install_cmd = runner._client.exec_command.call_args_list[1][0][0]
        assert "ansible" in install_cmd
        assert "apt-get install" in install_cmd

    # ── upload ────────────────────────────────────────────────────────

    def test_upload_inventory_correct_remote_path(self, tmp_path):
        """upload_inventory places the file at /home/admin/overtime/inventory/<name>."""
        runner = self._runner()
        sftp = MagicMock()
        runner._client.open_sftp.return_value.__enter__ = lambda s: sftp
        runner._client.open_sftp.return_value.__exit__  = lambda s, *_: None

        inv_file = tmp_path / "lab_inventory.yml"
        inv_file.write_text("all: {}")

        remote_path = runner.upload_inventory(inv_file)
        assert remote_path == "/home/admin/overtime/inventory/lab_inventory.yml"
        sftp.put.assert_called_once_with(str(inv_file), remote_path)

    def test_upload_playbooks_uploads_all_yml(self, tmp_path):
        """upload_playbooks uploads every .yml in the directory."""
        runner = self._runner()
        sftp = MagicMock()
        runner._client.open_sftp.return_value.__enter__ = lambda s: sftp
        runner._client.open_sftp.return_value.__exit__  = lambda s, *_: None

        # Create 3 yml files and 1 non-yml
        (tmp_path / "a.yml").write_text("")
        (tmp_path / "b.yml").write_text("")
        (tmp_path / "readme.md").write_text("")

        remote_dir = runner.upload_playbooks(tmp_path)
        assert remote_dir == "/home/admin/overtime/playbooks"
        assert sftp.put.call_count == 2  # only .yml files

    # ── run_step / _run_setup_jumphost ────────────────────────────────

    def test_run_step_builds_correct_command(self):
        """run_step assembles ansible-playbook with -i, --limit, -e."""
        runner = self._runner()

        # Mock _run_command
        runner._run_command = MagicMock(return_value=(0, "ok", 1.5))

        step = PlaybookStep(
            playbook="primary_ad_setup.yml",
            targets="ad",
            description="Primary AD setup",
            extra_vars={"dns_server": "10.0.0.1"},
        )
        result = runner.run_step(step, "/home/admin/overtime/inventory/inv.yml", "/home/admin/overtime/playbooks")

        runner._run_command.assert_called_once()
        cmd = runner._run_command.call_args[0][0]
        assert "ansible-playbook" in cmd
        assert "-i /home/admin/overtime/inventory/inv.yml" in cmd
        assert "/home/admin/overtime/playbooks/primary_ad_setup.yml" in cmd
        assert "--limit ad" in cmd
        assert "-e dns_server=10.0.0.1" in cmd
        assert result.exit_code == 0

    def test_run_setup_jumphost_uses_connection_local(self):
        """_run_setup_jumphost adds --connection local and skips inventory."""
        runner = self._runner()
        runner._run_command = MagicMock(return_value=(0, "ok", 2.0))

        step = PlaybookStep(
            playbook="setup_jumphost.yml",
            targets="lutil",
            description="Setup lutil",
        )
        result = runner._run_setup_jumphost(step, "/home/admin/overtime/playbooks")

        cmd = runner._run_command.call_args[0][0]
        assert "--connection local" in cmd
        assert "-i" not in cmd
        assert "-e" not in cmd
        assert result.exit_code == 0

    # ── run_plan ──────────────────────────────────────────────────────

    def test_run_plan_stops_on_first_failure(self):
        """run_plan halts at the first non-zero exit and does not continue."""
        runner = self._runner()

        # bootstrap_ansible: skip (already present)
        which_stdout = MagicMock()
        which_stdout.channel.recv_exit_status.return_value = 0

        # EXISTS checks: all return EXISTS
        exists_stdout = MagicMock()
        exists_stdout.read.return_value = b"EXISTS\n"

        runner._client.exec_command.side_effect = [
            # which ansible
            (None, which_stdout, MagicMock()),
            # mkdir -p inventory
            (None, MagicMock(), MagicMock()),
            # mkdir -p playbooks
            (None, MagicMock(), MagicMock()),
            # test -f step1
            (None, exists_stdout, MagicMock()),
            # step1 ansible-playbook → exit 1
            (None, self._failing_stdout(), self._stderr_mock()),
            # test -f step2 — should NOT be reached
            (None, exists_stdout, MagicMock()),
        ]

        # SFTP mock
        sftp = MagicMock()
        runner._client.open_sftp.return_value.__enter__ = lambda s: sftp
        runner._client.open_sftp.return_value.__exit__  = lambda s, *_: None

        plan = [
            PlaybookStep("probe_targets.yml", "all:!lutil", "Probe", {}),
            PlaybookStep("primary_ad_setup.yml", "ad", "Primary AD", {}),
        ]

        inv = Path("/dev/null")  # not actually read by mocked runner
        results = runner.run_plan(plan, inv, Path("."), skip_missing=True)

        # Only the first step executed (and failed)
        assert len(results) == 1
        assert results[0].exit_code != 0

    @staticmethod
    def _failing_stdout():
        m = MagicMock()
        m.channel.recv_exit_status.return_value = 1
        m.read.return_value = b"FAILED\n"
        return m

    def test_upload_ssh_key_places_key_and_sets_permissions(self, tmp_path):
        """upload_ssh_key resolves $HOME, copies the key, and chmods it 0600."""
        key_file = tmp_path / "id_rsa"
        key_file.write_text("PRIVATE KEY")

        runner = self._runner()

        # echo $HOME returns /home/admin
        home_stdout = MagicMock()
        home_stdout.read.return_value = b"/home/admin\n"
        # mkdir stdout — must support recv_exit_status for the wait
        mkdir_stdout = MagicMock()
        mkdir_stdout.channel.recv_exit_status.return_value = 0
        # chmod 600 call (default mock is fine)
        runner._client.exec_command.side_effect = [
            (None, home_stdout,  MagicMock()),  # echo $HOME
            (None, mkdir_stdout, MagicMock()),  # mkdir -p + chmod 700
            (None, MagicMock(),  MagicMock()),  # chmod 600
        ]

        sftp = MagicMock()
        runner._client.open_sftp.return_value.__enter__ = lambda s: sftp
        runner._client.open_sftp.return_value.__exit__  = lambda s, *_: None

        runner.upload_ssh_key(key_file)

        sftp.put.assert_called_once_with(str(key_file), "/home/admin/.ssh/ot_key")
        chmod_calls = [str(c) for c in runner._client.exec_command.call_args_list]
        assert any("chmod 600" in c for c in chmod_calls)

    @staticmethod
    def _stderr_mock():
        m = MagicMock()
        m.read.return_value = b"error details\n"
        return m


# ===========================================================================
# TestSetupWizard — 2 tests
# ===========================================================================


class TestSetupWizard:
    """default_playbooks_for(provider, scenario) → default playbook list."""

    def test_ad_lab_m_includes_secondary_ad(self):
        """ad-lab-m list contains secondary_ad_setup.yml (2 DCs)."""
        playbooks = default_playbooks_for("proxmox", "ad-lab-m")
        names = [p["playbook"] for p in playbooks]
        assert "secondary_ad_setup.yml" in names
        assert "primary_ad_setup.yml"   in names
        assert "join_member_server.yml" in names
        # WDAC is intentionally absent
        assert "wdac_deployment.yml"    not in names

    def test_jumphost_returns_setup_jumphost(self):
        """jumphost scenario includes setup_jumphost.yml."""
        playbooks = default_playbooks_for("proxmox", "jumphost")
        assert len(playbooks) == 1
        assert playbooks[0]["playbook"] == "setup_jumphost.yml"
        assert playbooks[0]["targets"] == "lutil"

    def test_k8s_dev_returns_cluster_setup(self):
        """k8s-dev scenario returns k8s_cluster_setup.yml targeting k8s group."""
        playbooks = default_playbooks_for("proxmox", "k8s-dev")
        assert len(playbooks) == 1
        assert playbooks[0]["playbook"] == "k8s_cluster_setup.yml"
        assert playbooks[0]["targets"] == "k8s"


# ===========================================================================
# TestSetupCommand — overtime setup CLI integration
# ===========================================================================


class TestSetupCommand:
    """Test the interactive `overtime setup` command via CliRunner."""

    # Proxmox prompts (password auth): provider, env_prefix, scenario, fqdn,
    #   use_token, api_url, user, tls_insecure, node, storage, bridge,
    #   linux_template, windows_template, subnet_cidr, gateway, vm_id_start,
    #   default_memory, ansible_user, ssh_pub_key
    _PROXMOX_INPUT = "\n".join([
        "proxmox",          # provider
        "lab",              # env prefix
        "ad-lab-m",         # scenario
        "lab.local",        # fqdn
        "n",                # use API token? → no (password mode)
        "https://10.0.0.1:8006",  # api url
        "root@pam",         # user
        "y",                # tls insecure
        "pve",              # node
        "local-lvm",        # storage
        "vmbr0",            # bridge
        "222",              # linux template
        "213",              # windows template
        "192.168.0.0/24", # subnet cidr
        "192.168.0.1",    # gateway
        "9000",             # vm_id_start
        "4096",             # default_memory
        "administrator",    # ansible user
        "ssh-ed25519 AAAA testkey",  # ssh pub key
        "~/.ssh/id_ed25519",  # ssh private key path
    ]) + "\n"

    # Proxmox prompts (API token auth)
    _PROXMOX_TOKEN_INPUT = "\n".join([
        "proxmox",          # provider
        "lab",              # env prefix
        "ad-lab-m",         # scenario
        "lab.local",        # fqdn
        "y",                # use API token? → yes
        "https://10.0.0.1:8006",  # api url
        "overtime@pve!ot-token",  # token ID
        "y",                # tls insecure
        "pve",              # node
        "local-lvm",        # storage
        "vmbr0",            # bridge
        "222",              # linux template
        "213",              # windows template
        "192.168.0.0/24", # subnet cidr
        "192.168.0.1",    # gateway
        "9000",             # vm_id_start
        "4096",             # default_memory
        "administrator",    # ansible user
        "ssh-ed25519 AAAA testkey",  # ssh pub key
        "~/.ssh/id_ed25519",  # ssh private key path
    ]) + "\n"

    _AZURE_INPUT = "\n".join([
        "azure",            # provider
        "lab",              # env prefix
        "k8s-dev",          # scenario
        "lab.local",        # fqdn
        "12345678-1234-1234-1234-123456789abc",  # subscription
        "ot-rg",            # resource group
        "eastus",           # location
        "ot-vnet",          # vnet name
        "10.0.0.0/16",      # vnet cidr
        "10.0.1.0/24",      # subnet cidr
        "Standard_B2s",     # vm size
        "overtimeadmin",    # admin username
        "*",                # allowed source IP
        "hladmin",          # ansible user
        "ssh-ed25519 AAAA testkey",  # ssh pub key
        "~/.ssh/id_ed25519",  # ssh private key path
    ]) + "\n"

    def test_setup_proxmox_writes_valid_yaml(self, tmp_path):
        """Proxmox setup produces a valid YAML file with expected structure."""
        out = tmp_path / "test-spec.yml"
        runner = CliRunner()
        result = runner.invoke(cli, ["setup", str(out)], input=self._PROXMOX_INPUT)

        assert result.exit_code == 0, result.output
        assert out.exists()

        data = yaml.safe_load(out.read_text())
        assert data["provider"] == "proxmox"
        assert data["proxmox"]["pm_api_url"] == "https://10.0.0.1:8006"
        assert data["proxmox"]["pm_password"] == "${secret:pm_password}"
        assert data["environment"]["scenario"] == "ad-lab-m"
        assert data["ansible"]["ansible_password"] == "${secret:ansible_password}"
        assert "ci_password" not in data["environment"]
        assert data["secrets"]["backend"] == "dotenv"

    def test_setup_azure_writes_valid_yaml(self, tmp_path):
        """Azure setup produces a valid YAML file with expected structure."""
        out = tmp_path / "azure-spec.yml"
        runner = CliRunner()
        result = runner.invoke(cli, ["setup", str(out)], input=self._AZURE_INPUT)

        assert result.exit_code == 0, result.output

        data = yaml.safe_load(out.read_text())
        assert data["provider"] == "azure"
        assert data["azure"]["subscription_id"] == "12345678-1234-1234-1234-123456789abc"
        assert data["azure"]["default_vm_size"] == "Standard_B2s"
        assert data["azure"]["allowed_source_prefix"] == "*"
        assert "proxmox" not in data
        assert data["ansible"]["ansible_user"] == "hladmin"

    def test_setup_includes_default_playbooks(self, tmp_path):
        """ad-lab-m setup populates configure.playbooks with defaults."""
        out = tmp_path / "ad-spec.yml"
        runner = CliRunner()
        result = runner.invoke(cli, ["setup", str(out)], input=self._PROXMOX_INPUT)

        assert result.exit_code == 0, result.output

        data = yaml.safe_load(out.read_text())
        assert "configure" in data
        names = [p["playbook"] for p in data["configure"]["playbooks"]]
        assert "primary_ad_setup.yml" in names
        assert "secondary_ad_setup.yml" in names

    def test_setup_jumphost_includes_setup_jumphost(self, tmp_path):
        """jumphost scenario includes setup_jumphost.yml in configure section."""
        jumphost_input = "\n".join([
            "proxmox", "ctrl", "jumphost", "ctrl.local",
            "n",  # use API token? → no (password mode)
            "https://10.0.0.1:8006", "root@pam", "y", "pve", "local-lvm",
            "vmbr0", "222", "213", "192.168.0.0/24", "192.168.0.1",
            "9000", "4096", "administrator", "ssh-ed25519 AAAA key",
            "~/.ssh/id_ed25519",  # ssh private key path
        ]) + "\n"
        out = tmp_path / "ctrl-spec.yml"
        runner = CliRunner()
        result = runner.invoke(cli, ["setup", str(out)], input=jumphost_input)

        assert result.exit_code == 0, result.output

        data = yaml.safe_load(out.read_text())
        assert data["environment"]["scenario"] == "jumphost"
        assert "configure" in data
        names = [p["playbook"] for p in data["configure"]["playbooks"]]
        assert names == ["setup_jumphost.yml"]

    def test_setup_refuses_overwrite_unless_confirmed(self, tmp_path):
        """Existing file triggers an overwrite prompt; 'n' aborts."""
        out = tmp_path / "existing.yml"
        out.write_text("old content")
        runner = CliRunner()
        # Answer 'n' to overwrite prompt
        result = runner.invoke(cli, ["setup", str(out)], input="n\n")

        assert result.exit_code != 0
        assert out.read_text() == "old content"

    def test_setup_proxmox_token_writes_valid_yaml(self, tmp_path):
        """Proxmox token auth setup produces spec with pm_api_token, not pm_password."""
        out = tmp_path / "token-spec.yml"
        runner = CliRunner()
        result = runner.invoke(cli, ["setup", str(out)], input=self._PROXMOX_TOKEN_INPUT)

        assert result.exit_code == 0, result.output
        assert out.exists()

        data = yaml.safe_load(out.read_text())
        assert data["provider"] == "proxmox"
        assert data["proxmox"]["pm_api_token"] == "${secret:pm_api_token}"
        assert data["proxmox"]["pm_user"] == "overtime@pve!ot-token"
        assert "pm_password" not in data["proxmox"]

    def test_setup_shows_next_steps(self, tmp_path):
        """Output includes next-steps guidance."""
        out = tmp_path / "spec.yml"
        runner = CliRunner()
        result = runner.invoke(cli, ["setup", str(out)], input=self._PROXMOX_INPUT)

        assert result.exit_code == 0
        assert "export PM_PASSWORD" in result.output
        assert "export ANSIBLE_PASSWORD" in result.output
        assert "overtime validate" in result.output

    def test_setup_token_shows_token_next_steps(self, tmp_path):
        """Token auth next-steps shows PM_API_TOKEN instead of PM_PASSWORD."""
        out = tmp_path / "spec.yml"
        runner = CliRunner()
        result = runner.invoke(cli, ["setup", str(out)], input=self._PROXMOX_TOKEN_INPUT)

        assert result.exit_code == 0
        assert "export PM_API_TOKEN" in result.output
        assert "PM_PASSWORD" not in result.output

    def test_setup_default_path(self, tmp_path, monkeypatch):
        """No output arg writes to configs/environments/<prefix>_<scenario>-provisioning-spec.yml."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["setup"], input=self._PROXMOX_INPUT)

        assert result.exit_code == 0, result.output
        expected = tmp_path / "configs" / "environments" / "lab_ad-lab-m-provisioning-spec.yml"
        assert expected.exists()
        data = yaml.safe_load(expected.read_text())
        assert data["environment"]["scenario"] == "ad-lab-m"
