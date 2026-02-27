"""Terraform orchestration for the Proxmox provider."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from .base import BaseOrchestrator
from .state import TerraformOutputs

logger = logging.getLogger(__name__)


class PveOrchestrator(BaseOrchestrator):
    """Manages the Terraform lifecycle for a Proxmox provisioning spec.

    Args:
        terraform_dir: Path to the ``terraform/`` directory.  Defaults to
                       ``./terraform`` relative to the current working directory.
    """

    def __init__(self, terraform_dir: Path = Path("terraform/proxmox")):
        super().__init__(terraform_dir)

    # ------------------------------------------------------------------
    # tfvars generation
    # ------------------------------------------------------------------

    def _write_tfvars(
        self,
        config: Dict[str, Any],
    ) -> Path:
        """Write ``terraform.tfvars.json``, excluding sensitive fields.

        ``pm_password`` and ``ansible_password`` are expected to already be
        in the environment (set by the CLI before calling the orchestrator).
        ``TF_VAR_ci_password`` is derived from ``ansible_password`` by the CLI.

        Returns:
            Path to the written tfvars file.
        """
        proxmox = config.get("proxmox", {})
        env = config.get("environment", {})
        ansible = config.get("ansible", {})

        tfvars = {
            "pm_api_url":                proxmox.get("pm_api_url"),
            "pm_user":                   proxmox.get("pm_user"),
            "pm_tls_insecure":           proxmox.get("pm_tls_insecure", False),
            "node_name":                 proxmox.get("node_name"),
            "storage_pool":              proxmox.get("storage_pool"),
            "network_bridge":            proxmox.get("network_bridge"),
            "linux_template_id":         int(proxmox.get("linux_template_id", 0)),
            "windows_template_id":       int(proxmox.get("windows_template_id", 0)),
            "scenario":                  env.get("scenario"),
            "environment_name_prefix":   env.get("environment_name_prefix"),
            "subnet_cidr":               proxmox.get("subnet_cidr"),
            "vm_gateway":                proxmox.get("vm_gateway"),
            "vm_id_start":               proxmox.get("vm_id_start", 9000),
            "default_memory":            proxmox.get("default_memory", 4096),
            "ssh_pub_key":               ansible.get("ssh_pub_key"),
            "ansible_user":              ansible.get("ansible_user", "ot-bootstrap"),
            "dns_servers":               [proxmox.get("vm_gateway", ""), "8.8.8.8"],
        }

        tfvars_path = self.terraform_dir / "terraform.tfvars.json"
        tfvars_path.write_text(json.dumps(tfvars, indent=2))
        logger.info(f"Wrote tfvars to {tfvars_path}")
        return tfvars_path

    # ------------------------------------------------------------------
    # Public lifecycle API
    # ------------------------------------------------------------------

    def plan(self, config: Dict[str, Any]) -> None:
        """Generate tfvars, select workspace, and run ``terraform plan``."""
        prefix = config["environment"]["environment_name_prefix"]
        scenario = config["environment"]["scenario"]

        self._write_tfvars(config)
        self.ensure_workspace(prefix, scenario)

        self._run(["plan", "-input=false"] + self._var_args())

    def apply(
        self, config: Dict[str, Any], *, auto_approve: bool = False
    ) -> TerraformOutputs:
        """Generate tfvars, select workspace, apply, and return outputs."""
        prefix = config["environment"]["environment_name_prefix"]
        scenario = config["environment"]["scenario"]

        self._write_tfvars(config)
        self.ensure_workspace(prefix, scenario)

        args = ["apply", "-input=false"] + self._var_args()
        if auto_approve:
            args.append("-auto-approve")
        self._run(args)

        return self.read_outputs()

    def destroy(
        self, config: Dict[str, Any], *, auto_approve: bool = False
    ) -> None:
        """Write tfvars, select workspace, and run ``terraform destroy``."""
        prefix = config["environment"]["environment_name_prefix"]
        scenario = config["environment"]["scenario"]
        self._write_tfvars(config)
        self.ensure_workspace(prefix, scenario)

        args = ["destroy", "-input=false"] + self._var_args()
        if auto_approve:
            args.append("-auto-approve")
        self._run(args)

    # ------------------------------------------------------------------
    # VM definition helper (public, used by configure command)
    # ------------------------------------------------------------------

    def get_vm_definitions(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Load VM definitions for the environment in *config*."""
        scenario = config["environment"]["scenario"]
        return self._load_vm_definitions(scenario)
