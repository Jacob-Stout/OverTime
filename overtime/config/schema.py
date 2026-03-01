"""Pydantic schemas for configuration validation."""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator, SecretStr


class VmSpec(BaseModel):
    """A single VM definition in the provisioning spec."""

    name: str = Field(
        ...,
        min_length=1,
        description="Name suffix — the VM will be named {environment_name_prefix}-{name}",
        examples=["ad-1a", "lutil-1a", "k8s-1a"],
    )
    os: Literal["windows", "linux"] = Field(
        ...,
        description="Operating system type",
    )
    role: str = Field(
        ...,
        min_length=1,
        description="VM role used for Ansible inventory grouping "
                    "(e.g. ad, wutil, general, ctrl, work, lutil)",
    )
    cpu: int = Field(
        default=2,
        ge=1,
        description="Number of CPU cores",
    )
    memory: Optional[int] = Field(
        default=None,
        ge=512,
        description="RAM in MB. Omit to use the provider default.",
    )
    disk: int = Field(
        default=40,
        ge=1,
        description="Disk size in GB",
    )
    ip_offset: int = Field(
        ...,
        ge=0,
        description="Offset added to the subnet base to calculate this VM's IP address",
    )


class ProxmoxConfig(BaseModel):
    """Proxmox provider configuration."""

    pm_api_url: str = Field(
        ...,
        description="Proxmox API URL",
        examples=["https://192.168.0.100:8006"]
    )
    pm_user: str = Field(
        ...,
        description="Proxmox username (e.g. root@pam) or API token ID (e.g. overtime@pve!overtime-token)",
        examples=["root@pam", "overtime@pve!overtime-token"]
    )
    pm_password: Optional[SecretStr] = Field(
        default=None,
        description="Proxmox password (use secret reference). Mutually exclusive with pm_api_token."
    )
    pm_api_token: Optional[SecretStr] = Field(
        default=None,
        description="Proxmox API token secret (use secret reference). Mutually exclusive with pm_password."
    )
    pm_tls_insecure: bool = Field(
        default=False,
        description="Skip TLS certificate verification"
    )
    node_name: str = Field(
        ...,
        description="Proxmox node name"
    )
    storage_pool: str = Field(
        ...,
        description="Storage pool for VMs"
    )
    network_bridge: str = Field(
        ...,
        description="Network bridge",
        examples=["vmbr0", "vmbr2"]
    )
    linux_template_id: str = Field(
        ...,
        description="Linux template VM ID or name"
    )
    windows_template_id: str = Field(
        ...,
        description="Windows template VM ID or name"
    )
    subnet_cidr: str = Field(
        ...,
        description="Subnet CIDR for VM addressing (e.g. 192.168.0.0/24)",
        examples=["192.168.0.0/24", "10.0.1.0/24"]
    )
    vm_gateway: str = Field(
        ...,
        description="Default gateway IP for VMs",
        examples=["192.168.0.1", "10.0.1.1"]
    )
    vm_id_start: int = Field(
        default=9000,
        description="Starting VM ID for Proxmox. Each VM gets vm_id_start + list index.",
        ge=100,
        le=999999,
    )
    default_memory: int = Field(
        default=4096,
        description="Default RAM in MB for VMs that omit a memory value.",
        ge=512,
    )

    @field_validator('pm_api_url')
    @classmethod
    def validate_api_url(cls, v: str) -> str:
        """Ensure API URL uses HTTPS."""
        if not v.startswith('https://'):
            raise ValueError('Proxmox API URL must use HTTPS')
        return v.rstrip('/')  # Remove trailing slash

    @field_validator('subnet_cidr')
    @classmethod
    def validate_subnet_cidr(cls, v: str) -> str:
        """Validate CIDR notation (X.X.X.X/N)."""
        parts = v.split('/')
        if len(parts) != 2:
            raise ValueError('subnet_cidr must be in CIDR notation (e.g. 192.168.0.0/24)')
        ip, prefix = parts
        octets = ip.split('.')
        if len(octets) != 4:
            raise ValueError('Invalid IP address in CIDR')
        try:
            for octet in octets:
                num = int(octet)
                if not 0 <= num <= 255:
                    raise ValueError('IP octet must be 0-255')
            prefix_num = int(prefix)
            if not 0 <= prefix_num <= 32:
                raise ValueError('CIDR prefix must be 0-32')
        except ValueError:
            raise ValueError('Invalid CIDR notation')
        return v

    @field_validator('vm_gateway')
    @classmethod
    def validate_gateway_ip(cls, v: str) -> str:
        """Basic IP validation for gateway."""
        parts = v.split('.')
        if len(parts) != 4:
            raise ValueError('Invalid IP address format')
        try:
            for part in parts:
                num = int(part)
                if not 0 <= num <= 255:
                    raise ValueError('IP octet must be 0-255')
        except ValueError:
            raise ValueError('Invalid IP address')
        return v

    @model_validator(mode='after')
    def validate_auth_method(self):
        """Exactly one of pm_password or pm_api_token must be provided."""
        has_password = self.pm_password is not None
        has_token = self.pm_api_token is not None
        if has_password and has_token:
            raise ValueError(
                'Specify either pm_password or pm_api_token, not both'
            )
        if not has_password and not has_token:
            raise ValueError(
                'Either pm_password or pm_api_token is required'
            )
        return self


class EnvironmentConfig(BaseModel):
    """Environment definition."""

    environment_name_prefix: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Prefix for VM names",
        examples=["lab", "prod"]
    )
    environment_fqdn: str = Field(
        ...,
        description="Fully qualified domain name",
        examples=["lab.local", "homelab.internal"]
    )
    workspace: str = Field(
        ...,
        min_length=1,
        max_length=30,
        pattern=r'^[a-zA-Z0-9][a-zA-Z0-9-]*$',
        description="Terraform workspace name. Each spec must use a unique workspace "
                    "to isolate its state. Auto-populated by `overtime setup` when a "
                    "scenario is selected (e.g. lab-ad-lab-m).",
        examples=["lab-ad-lab-m", "prod-jumphost", "my-custom-lab"]
    )


class AnsibleConfig(BaseModel):
    """Ansible configuration."""

    ansible_user: str = Field(
        ...,
        min_length=1,
        description="Ansible user for VM access"
    )
    ansible_password: SecretStr = Field(
        ...,
        min_length=1,
        description="Ansible user password"
    )
    ssh_pub_key: str = Field(
        ...,
        description="SSH public key for Linux VMs"
    )
    ssh_key: Optional[str] = Field(
        default=None,
        description="Path to SSH private key file"
    )


class SecretConfig(BaseModel):
    """Secret management configuration."""

    backend: Literal['envvars', 'dotenv'] = Field(
        default='dotenv',
        description="Default secret backend for plain keys. "
                    "op:// keys are always routed to 1Password regardless of this setting."
    )
    dotenv_path: Optional[str] = Field(
        default=None,
        description="Path to .env file (default: .env in project root). "
                    "Only used when backend=dotenv."
    )


class AzureConfig(BaseModel):
    """Azure provider configuration."""

    subscription_id: str = Field(
        ...,
        description="Azure subscription ID (UUID)",
    )
    resource_group: str = Field(
        ...,
        description="Resource group name. Created by Terraform if it does not exist.",
        examples=["ot-lab-M", "ot-dev-eastus"],
    )
    location: str = Field(
        ...,
        description="Azure region",
        examples=["eastus", "westeurope", "australiaeast"],
    )
    vnet_name: str = Field(
        ...,
        description="Virtual network name",
        examples=["ot-vnet"],
    )
    vnet_cidr: str = Field(
        ...,
        description="VNet address space (CIDR)",
        examples=["10.0.0.0/16"],
    )
    subnet_cidr: str = Field(
        ...,
        description="Subnet address space (must be within vnet_cidr)",
        examples=["10.0.1.0/24"],
    )
    default_vm_size: str = Field(
        default="Standard_B2s",
        description="Default Azure VM size for VMs that omit a vm_size value.",
        examples=["Standard_B2s", "Standard_D2s_v3"],
    )
    admin_username: str = Field(
        default="overtimeadmin",
        description="VM administrator username. Cannot be a reserved name on Windows.",
    )
    allowed_source_prefix: str = Field(
        default="*",
        description="Source IP/CIDR for inbound NSG rules (SSH, RDP, WinRM). "
                    "Set to your public IP (e.g. '203.0.113.5/32') for internet-facing labs.",
    )

    @field_validator('subscription_id')
    @classmethod
    def validate_subscription_id(cls, v: str) -> str:
        """Basic UUID format check."""
        import re
        if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', v, re.IGNORECASE):
            raise ValueError('subscription_id must be a valid UUID')
        return v

    @field_validator('admin_username')
    @classmethod
    def validate_admin_username(cls, v: str) -> str:
        """Azure rejects certain reserved usernames."""
        reserved = {'administrator', 'admin', 'user', 'test', 'guest', 'master', 'root'}
        if v.lower() in reserved:
            raise ValueError(f'Azure rejects reserved username: {v}')
        return v


class PlaybookEntry(BaseModel):
    """One entry in the configure.playbooks list."""

    playbook: str = Field(..., description="Playbook filename (relative to ansible/)")
    targets: str = Field(..., description="Ansible host-group pattern for --limit")
    description: Optional[str] = Field(default=None, description="Human-readable label (defaults to playbook filename)")


class JumphostConfig(BaseModel):
    """jumphost section of the provisioning spec."""

    ip: Optional[str] = Field(default=None, description="Explicit IP for the linux utility server.  Omit to auto-discover from Terraform outputs.")


class ConfigureConfig(BaseModel):
    """configure section — explicit playbook sequence."""

    playbooks: list[PlaybookEntry] = Field(default_factory=list, description="Ordered playbook list.  System steps are prepended automatically.")


class ProvisioningSpec(BaseModel):
    """Complete provisioning specification."""

    provider: Literal['proxmox', 'azure'] = Field(
        default='proxmox',
        description="Infrastructure provider"
    )
    proxmox: Optional[ProxmoxConfig] = Field(
        default=None,
        description="Proxmox configuration (required if provider=proxmox)"
    )
    azure: Optional[AzureConfig] = Field(
        default=None,
        description="Azure configuration (required if provider=azure)"
    )
    environment: EnvironmentConfig
    ansible: AnsibleConfig
    vms: list[VmSpec] = Field(
        ...,
        min_length=1,
        description="VM definitions. Each entry describes one VM to provision.",
    )
    secrets: SecretConfig = Field(default_factory=SecretConfig)
    jumphost: Optional[JumphostConfig] = Field(default=None, description="Linux utility server (jumphost) settings")
    configure: Optional[ConfigureConfig] = Field(default=None, description="Explicit playbook sequence for overtime configure")

    @model_validator(mode='after')
    def validate_provider_config(self):
        """Ensure the provider-specific config block is present."""
        if self.provider == 'proxmox' and self.proxmox is None:
            raise ValueError('Proxmox configuration required when provider=proxmox')
        if self.provider == 'azure' and self.azure is None:
            raise ValueError('Azure configuration required when provider=azure')
        return self

    @model_validator(mode='after')
    def validate_unique_vm_names(self):
        """Ensure VM names are unique."""
        names = [vm.name for vm in self.vms]
        dupes = [n for n in names if names.count(n) > 1]
        if dupes:
            raise ValueError(f'Duplicate VM names: {sorted(set(dupes))}')
        return self

    @model_validator(mode='after')
    def validate_unique_ip_offsets(self):
        """Ensure IP offsets are unique."""
        offsets = [vm.ip_offset for vm in self.vms]
        dupes = [o for o in offsets if offsets.count(o) > 1]
        if dupes:
            raise ValueError(f'Duplicate ip_offset values: {sorted(set(dupes))}')
        return self

    @model_validator(mode='after')
    def validate_azure_ssh_key_pairing(self):
        """Azure disables password auth when ssh_pub_key is set; require ssh_key."""
        if (
            self.provider == 'azure'
            and self.ansible.ssh_pub_key
            and not self.ansible.ssh_key
        ):
            raise ValueError(
                'ssh_key (private key path) is required when ssh_pub_key is set '
                'with provider=azure. Azure disables password authentication on '
                'Linux VMs when an SSH public key is provided.'
            )
        return self

    model_config = {
        'extra': 'forbid',  # Reject unknown fields
    }
