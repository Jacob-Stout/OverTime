"""Terraform orchestration for the Azure provider."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from .base import BaseOrchestrator
from .state import TerraformOutputs

logger = logging.getLogger(__name__)


class AzureOrchestrator(BaseOrchestrator):
    """Manages the Terraform lifecycle for an Azure provisioning spec.

    Args:
        terraform_dir: Path to the ``terraform/azure/`` directory.
    """

    def __init__(self, terraform_dir: Path = Path("terraform/azure")):
        super().__init__(terraform_dir)

    # ------------------------------------------------------------------
    # tfvars generation
    # ------------------------------------------------------------------

    def _write_tfvars(self, config: Dict[str, Any]) -> Path:
        """Write ``terraform.tfvars.json`` for the Azure root module.

        ``admin_password`` is excluded — it is passed via ``TF_VAR_admin_password``.
        """
        azure_cfg = config["azure"]
        env_cfg   = config["environment"]

        # Convert VM list to the format Terraform expects
        vm_list = [
            {
                "name_suffix": vm["name"],
                "role":        vm["role"],
                "os_type":     vm["os"],
                "ip_offset":   vm["ip_offset"],
                "disk_gb":     vm.get("disk", 30),
            }
            for vm in config.get("vms", [])
        ]

        tfvars = {
            "subscription_id":         azure_cfg["subscription_id"],
            "resource_group_name":     azure_cfg["resource_group"],
            "vnet_name":               azure_cfg["vnet_name"],
            "vnet_cidr":               azure_cfg["vnet_cidr"],
            "subnet_cidr":             azure_cfg["subnet_cidr"],
            "environment_name_prefix": env_cfg["environment_name_prefix"],
            "workspace":               env_cfg["workspace"],
            "admin_username":          azure_cfg["admin_username"],
            "ssh_pub_key":             config["ansible"]["ssh_pub_key"],
            "default_vm_size":         azure_cfg["default_vm_size"],
            "allowed_source_prefix":   azure_cfg["allowed_source_prefix"],
            "vm_list":                 vm_list,
        }

        tfvars_path = self.terraform_dir / "terraform.tfvars.json"
        tfvars_path.write_text(json.dumps(tfvars, indent=2))
        logger.info(f"Wrote tfvars to {tfvars_path}")
        return tfvars_path

    # ------------------------------------------------------------------
    # Environment setup
    # ------------------------------------------------------------------

    def _set_env(self, config: Dict[str, Any]) -> None:
        """Register admin_password as a ``-var`` arg for Terraform.

        ARM_SUBSCRIPTION_ID is set on ``_extra_env`` by ``_make_orchestrator()``
        (cli.py) before any Terraform command runs.
        """
        self._tf_vars["admin_password"] = config["ansible"]["ansible_password"]
        logger.debug("Registered admin_password as -var arg")

    # ------------------------------------------------------------------
    # Public lifecycle API
    # ------------------------------------------------------------------

    def plan(self, config: Dict[str, Any]) -> None:
        """Generate tfvars, set env, select workspace, run plan."""
        self._set_env(config)
        self._write_tfvars(config)
        self.ensure_workspace(config["environment"]["workspace"])
        self._run(["plan", "-input=false"] + self._var_args())

    def apply(self, config: Dict[str, Any], *, auto_approve: bool = False) -> TerraformOutputs:
        """Generate tfvars, set env, select workspace, apply, return outputs.

        After a successful apply, disables the Windows Firewall on every
        Windows VM via ``az vm run-command invoke``.
        """
        self._set_env(config)
        vms = config.get("vms", [])
        self._write_tfvars(config)
        self.ensure_workspace(config["environment"]["workspace"])

        args = ["apply", "-input=false"] + self._var_args()
        if auto_approve:
            args.append("-auto-approve")
        self._run(args)

        outputs = self.read_outputs()

        # Disable Windows Firewall on all Windows VMs so Ansible/WinRM can connect.
        windows_vms = [vm for vm in vms if vm["os"] == "windows"]
        if windows_vms:
            rg = config["azure"]["resource_group"]
            prefix = config["environment"]["environment_name_prefix"]
            self._disable_windows_firewall(windows_vms, rg, prefix)

        return outputs

    def destroy(self, config: Dict[str, Any], *, auto_approve: bool = False) -> None:
        """Write tfvars, select workspace, and run destroy."""
        self._set_env(config)
        self._write_tfvars(config)
        self.ensure_workspace(config["environment"]["workspace"])

        args = ["destroy", "-input=false"] + self._var_args()
        if auto_approve:
            args.append("-auto-approve")
        self._run(args)

    # ------------------------------------------------------------------
    # Post-apply: disable Windows Firewall via Azure Run Command
    # ------------------------------------------------------------------

    def _disable_windows_firewall(
        self, windows_vms: List[Dict[str, Any]], resource_group: str, prefix: str
    ) -> None:
        """Run ``az vm run-command invoke`` on each Windows VM to disable the firewall."""
        if not shutil.which("az"):
            logger.warning("Azure CLI ('az') not found; skipping firewall disable")
            return

        script = "Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False"

        for vm in windows_vms:
            vm_name = f"{prefix}-{vm['name']}"
            logger.info(f"Disabling Windows Firewall on {vm_name} …")

            result = subprocess.run(
                [
                    "az", "vm", "run-command", "invoke",
                    "--command-id", "RunPowerShellScript",
                    "--name", vm_name,
                    "--resource-group", resource_group,
                    "--scripts", script,
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                logger.info(f"Firewall disabled on {vm_name}")
            else:
                logger.warning(
                    f"Failed to disable firewall on {vm_name} (exit {result.returncode}): "
                    f"{result.stderr.strip()}"
                )
