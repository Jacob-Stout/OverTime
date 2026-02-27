"""Terraform orchestration for shared Azure network infrastructure."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from .base import BaseOrchestrator
from .state import TerraformOutputs
from ..utils.exceptions import TerraformError

logger = logging.getLogger(__name__)


class AzureNetworkOrchestrator(BaseOrchestrator):
    """Manages the Terraform lifecycle for shared Azure network infra (RG + VNet).

    This orchestrator manages ``terraform/azure-network/`` which contains only
    the Resource Group and Virtual Network.  These resources are shared across
    all Azure scenarios in the same environment.

    Workspace naming: ``net-{prefix}`` (e.g. ``net-azlab``).
    """

    def __init__(self, terraform_dir: Path = Path("terraform/azure-network")):
        super().__init__(terraform_dir)

    # ------------------------------------------------------------------
    # Workspace — different naming convention than per-scenario
    # ------------------------------------------------------------------

    def ensure_network_workspace(self, prefix: str) -> None:
        """Select workspace ``net-{prefix}``, creating if needed."""
        workspace = f"net-{prefix}"
        result = self._run(
            ["workspace", "select", workspace],
            check=False,
            capture=True,
        )
        if result.returncode == 0:
            logger.info(f"Selected workspace: {workspace}")
            return
        self._run(["workspace", "new", workspace])
        logger.info(f"Created workspace: {workspace}")

    # ------------------------------------------------------------------
    # tfvars
    # ------------------------------------------------------------------

    def _write_tfvars(self, config: Dict[str, Any]) -> Path:
        """Write ``terraform.tfvars.json`` for the network root module."""
        azure_cfg = config["azure"]
        env_cfg = config["environment"]

        tfvars = {
            "subscription_id":     azure_cfg["subscription_id"],
            "resource_group_name": azure_cfg["resource_group"],
            "location":            azure_cfg["location"],
            "vnet_name":           azure_cfg["vnet_name"],
            "vnet_cidr":           azure_cfg["vnet_cidr"],
            "environment_name_prefix": env_cfg["environment_name_prefix"],
        }

        tfvars_path = self.terraform_dir / "terraform.tfvars.json"
        tfvars_path.write_text(json.dumps(tfvars, indent=2))
        logger.info(f"Wrote network tfvars to {tfvars_path}")
        return tfvars_path

    # ------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------

    def _set_env(self, config: Dict[str, Any]) -> None:
        """Register ARM_SUBSCRIPTION_ID in the subprocess environment."""
        self._extra_env["ARM_SUBSCRIPTION_ID"] = config["azure"]["subscription_id"]
        logger.debug("Set ARM_SUBSCRIPTION_ID for network orchestrator")

    # ------------------------------------------------------------------
    # Public lifecycle API
    # ------------------------------------------------------------------

    def plan(self, config: Dict[str, Any]) -> None:
        """Write tfvars, select workspace, run ``terraform plan``."""
        self._set_env(config)
        self._write_tfvars(config)
        self.ensure_network_workspace(config["environment"]["environment_name_prefix"])
        self._run(["plan", "-input=false"])

    def apply(
        self, config: Dict[str, Any], *, auto_approve: bool = False
    ) -> TerraformOutputs:
        """Write tfvars, select workspace, apply, return outputs."""
        self._set_env(config)
        self._write_tfvars(config)
        self.ensure_network_workspace(config["environment"]["environment_name_prefix"])
        args = ["apply", "-input=false"]
        if auto_approve:
            args.append("-auto-approve")
        self._run(args)
        return self.read_outputs()

    def destroy(
        self, config: Dict[str, Any], *, auto_approve: bool = False
    ) -> None:
        """Write tfvars, select workspace, and run ``terraform destroy``."""
        self._set_env(config)
        self._write_tfvars(config)
        self.ensure_network_workspace(config["environment"]["environment_name_prefix"])
        args = ["destroy", "-input=false"]
        if auto_approve:
            args.append("-auto-approve")
        self._run(args)

    def get_vm_definitions(
        self, config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Network module has no VMs."""
        raise TerraformError(
            "AzureNetworkOrchestrator does not manage VMs",
            details="Use AzureOrchestrator for VM operations.",
        )
