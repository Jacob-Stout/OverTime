"""Tests for configuration loading."""

import pytest
from pathlib import Path
from overtime.config.loader import load_yaml, load_provisioning_spec
from overtime.utils.exceptions import ConfigurationError


def test_load_valid_yaml(tmp_path):
    """Test loading valid YAML file."""
    config_file = tmp_path / "test.yml"
    config_file.write_text("key: value\n")

    data = load_yaml(config_file)
    assert data == {'key': 'value'}


def test_load_nonexistent_file():
    """Test loading non-existent file raises error."""
    with pytest.raises(ConfigurationError, match="not found"):
        load_yaml(Path("/nonexistent/file.yml"))


def test_load_invalid_yaml(tmp_path):
    """Test loading invalid YAML raises error."""
    config_file = tmp_path / "invalid.yml"
    config_file.write_text("invalid: yaml: syntax:\n")

    with pytest.raises(ConfigurationError, match="Invalid YAML"):
        load_yaml(config_file)


def test_validate_provisioning_spec(tmp_path):
    """Test provisioning spec validation."""
    config_file = tmp_path / "spec.yml"
    config_file.write_text("""
provider: proxmox
proxmox:
  pm_api_url: https://192.168.0.100:8006
  pm_user: root@pam
  pm_password: password
  node_name: pve
  storage_pool: local-lvm
  network_bridge: vmbr0
  linux_template_id: ubuntu-template
  windows_template_id: windows-template
  subnet_cidr: 192.168.0.0/24
  vm_gateway: 192.168.0.1
environment:
  environment_name_prefix: test
  scenario: jumphost
  environment_fqdn: test.local
ansible:
  ansible_user: admin
  ansible_password: password
  ssh_pub_key: ssh-ed25519 AAAA... user@host
""")

    spec = load_provisioning_spec(config_file)
    assert spec.provider == 'proxmox'
    assert spec.environment.scenario == 'jumphost'


def test_invalid_api_url_rejected(tmp_path):
    """Test that HTTP API URLs are rejected."""
    config_file = tmp_path / "spec.yml"
    config_file.write_text("""
provider: proxmox
proxmox:
  pm_api_url: http://insecure:8006
  pm_user: root@pam
  pm_password: password
  node_name: pve
  storage_pool: local-lvm
  network_bridge: vmbr0
  linux_template_id: ubuntu
  windows_template_id: windows
  subnet_cidr: 192.168.0.0/24
  vm_gateway: 192.168.0.1
environment:
  environment_name_prefix: test
  scenario: jumphost
  environment_fqdn: test.local
ansible:
  ansible_user: admin
  ansible_password: password
  ssh_pub_key: ssh-ed25519 AAAA... user@host
""")

    with pytest.raises(ConfigurationError, match="must use HTTPS"):
        load_provisioning_spec(config_file)


def test_proxmox_ssh_pub_key_without_ssh_key_passes(tmp_path):
    """Proxmox allows ssh_pub_key without ssh_key (password auth stays enabled)."""
    config_file = tmp_path / "spec.yml"
    config_file.write_text("""
provider: proxmox
proxmox:
  pm_api_url: https://192.168.0.100:8006
  pm_user: root@pam
  pm_password: password
  node_name: pve
  storage_pool: local-lvm
  network_bridge: vmbr0
  linux_template_id: ubuntu-template
  windows_template_id: windows-template
  subnet_cidr: 192.168.0.0/24
  vm_gateway: 192.168.0.1
environment:
  environment_name_prefix: test
  scenario: jumphost
  environment_fqdn: test.local
ansible:
  ansible_user: admin
  ansible_password: password
  ssh_pub_key: ssh-ed25519 AAAA... user@host
""")

    spec = load_provisioning_spec(config_file)
    assert spec.ansible.ssh_pub_key == "ssh-ed25519 AAAA... user@host"
    assert spec.ansible.ssh_key is None


def test_invalid_ip_address_rejected(tmp_path):
    """Test that invalid IP addresses are rejected."""
    config_file = tmp_path / "spec.yml"
    config_file.write_text("""
provider: proxmox
proxmox:
  pm_api_url: https://192.168.0.100:8006
  pm_user: root@pam
  pm_password: password
  node_name: pve
  storage_pool: local-lvm
  network_bridge: vmbr0
  linux_template_id: ubuntu
  windows_template_id: windows
  subnet_cidr: 192.168.0.0/24
  vm_gateway: 999.999.999.999
environment:
  environment_name_prefix: test
  scenario: jumphost
  environment_fqdn: test.local
ansible:
  ansible_user: admin
  ansible_password: password
  ssh_pub_key: ssh-ed25519 AAAA... user@host
""")

    with pytest.raises(ConfigurationError, match="Invalid IP"):
        load_provisioning_spec(config_file)
