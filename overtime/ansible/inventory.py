"""Ansible inventory generation from Terraform state."""

import logging
from typing import Dict, List, Optional

import yaml

from ..terraform.state import TerraformOutputs
from ..utils.exceptions import OvertimeError

logger = logging.getLogger(__name__)


class InventoryGenerationError(OvertimeError):
    """Raised when inventory generation fails."""


# VM role tag → Ansible group name.  Roles not listed here use the tag directly.
_ROLE_GROUP_MAP: Dict[str, str] = {
    "ad":      "ad",
    "wutil":   "wutil",
    "general": "general",
    "ctrl":    "k8s_ctrl",   # ctrl-role VMs are K8s control-plane nodes
    "work":    "k8s_work",   # work-role VMs are K8s worker nodes
    "lutil":   "lutil",
}

# Child → parent group.  Groups with a parent are nested under it in the
# inventory so that Ansible can target e.g. ``k8s`` (all), ``k8s_ctrl``
# (control-plane only), or ``k8s_ctrl[0]`` (first control-plane node).
_PARENT_GROUP: Dict[str, str] = {
    "k8s_ctrl": "k8s",
    "k8s_work": "k8s",
}


def _connection_vars_for(os_type: str) -> Dict[str, object]:
    """Return Ansible connection vars for a given VM os_type."""
    if os_type == "windows":
        return {
            "ansible_connection":                   "winrm",
            "ansible_winrm_transport":              "ntlm",
            "ansible_winrm_server_cert_validation": "ignore",
            "ansible_winrm_port":                   5985,
        }
    return {"ansible_connection": "ssh"}


class AnsibleInventoryGenerator:
    """Generates Ansible inventory YAML from Terraform outputs and VM definitions.

    The generator needs *both* Terraform outputs (actual IPs from state) and
    the original VM definition list (for role information, which is not exposed
    as a Terraform output).

    Args:
        outputs:              Parsed Terraform outputs.
        vm_definitions:       VM definition list for the environment (same
                              structure as ``locals.vm_definitions`` in main.tf,
                              with variable references already resolved).
        name_prefix:          Environment name prefix (e.g. ``"lab"``).
        fqdn:                 Environment FQDN (e.g. ``"lab.local"``).
        ansible_user:         Ansible connection username.
        ansible_password:     Ansible connection password.
    """

    def __init__(
        self,
        outputs: TerraformOutputs,
        vm_definitions: List[Dict],
        *,
        name_prefix: str,
        fqdn: str,
        ansible_user: str,
        ansible_password: str,
        ssh_key_path: Optional[str] = None,
    ):
        self._outputs = outputs
        self._vm_definitions = vm_definitions
        self._name_prefix = name_prefix
        self._fqdn = fqdn
        self._ansible_user = ansible_user
        self._ansible_password = ansible_password
        self._ssh_key_path = ssh_key_path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_role_map(self) -> Dict[str, List[Dict]]:
        """Group VM definitions by Ansible group name."""
        groups: Dict[str, List[Dict]] = {}
        for vm in self._vm_definitions:
            group = _ROLE_GROUP_MAP.get(vm["role"], vm["role"])
            groups.setdefault(group, []).append(vm)
        return groups

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> Dict:
        """Build the inventory dict.

        Returns:
            Inventory dict matching Ansible's YAML inventory schema.

        Raises:
            InventoryGenerationError: If a VM from definitions has no matching
                                      IP in the Terraform outputs.
        """
        ip_map = self._outputs.all_vm_ips  # name → IP with CIDR

        # -- all-group vars (common to every host) -------------------------
        all_vars: Dict = {
            "ansible_user":          self._ansible_user,
            "ansible_password":      self._ansible_password,
            "ansible_domain_prefix": self._name_prefix,
            "ansible_env_fqdn":      self._fqdn,
        }
        if self._ssh_key_path:
            all_vars["ansible_ssh_private_key_file"] = self._ssh_key_path

        # -- children groups -----------------------------------------------
        flat_groups: Dict = {}
        for group, vms in self._build_role_map().items():
            hosts: Dict = {}
            for vm in vms:
                hostname = f"{self._name_prefix}-{vm['name_suffix']}"
                ip_with_cidr = ip_map.get(hostname)

                if ip_with_cidr is None:
                    raise InventoryGenerationError(
                        f"No Terraform output IP for VM '{hostname}'",
                        details="Run 'overtime create' first to provision the VMs.",
                    )

                # Strip CIDR for ansible_host
                ip = ip_with_cidr.split("/")[0]
                hosts[hostname] = {"ansible_host": ip}

            # Connection vars per group based on os_type
            group_vars = _connection_vars_for(vms[0].get("os_type", "cloud-init"))
            flat_groups[group] = {"hosts": hosts, "vars": group_vars}

        # -- nest child groups under parents (e.g. k8s_ctrl → k8s) ---------
        children: Dict = {}
        for group, data in flat_groups.items():
            parent = _PARENT_GROUP.get(group)
            if parent:
                children.setdefault(parent, {"children": {}})
                children[parent]["children"][group] = data
            else:
                children[group] = data

        return {
            "all": {
                "vars":    all_vars,
                "children": children,
            }
        }

    def to_yaml(self) -> str:
        """Return the inventory as a YAML string."""
        return yaml.dump(self.generate(), default_flow_style=False, sort_keys=False)
