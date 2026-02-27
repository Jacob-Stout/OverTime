"""Abstract base class for Terraform orchestrators."""

import logging
import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List

import hcl2

from ..utils.exceptions import TerraformError
from .state import TerraformOutputs

logger = logging.getLogger(__name__)


class BaseOrchestrator(ABC):
    """Shared Terraform lifecycle logic for all providers.

    Subclasses must implement the four abstract methods that differ between
    providers: :meth:`plan`, :meth:`apply`, :meth:`destroy`, and
    :meth:`get_vm_definitions`.

    Args:
        terraform_dir: Path to the provider's Terraform root directory.
    """

    def __init__(self, terraform_dir: Path):
        self.terraform_dir = terraform_dir.resolve()
        self._extra_env: Dict[str, str] = {}
        self._tf_vars: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Subprocess helper
    # ------------------------------------------------------------------

    def _run(
        self,
        args: List[str],
        *,
        check: bool = True,
        capture: bool = False,
    ) -> subprocess.CompletedProcess:
        """Run a ``terraform`` sub-command in ``self.terraform_dir``.

        Raises:
            TerraformError: If the command exits non-zero and *check* is True.
        """
        cmd = ["terraform"] + args
        logger.debug(f"Running: {' '.join(cmd)}")
        run_env = {**os.environ, **self._extra_env} if self._extra_env else None

        try:
            result = subprocess.run(
                cmd,
                cwd=self.terraform_dir,
                capture_output=capture,
                text=True,
                env=run_env,
            )
        except FileNotFoundError:
            raise TerraformError(
                "Terraform executable not found. "
                "Please install Terraform and ensure it is on your PATH."
            )

        if check and result.returncode != 0:
            stderr = result.stderr if capture else "(stderr not captured)"
            raise TerraformError(
                f"terraform {args[0]} failed (exit {result.returncode})",
                details=stderr,
            )
        return result

    def _var_args(self) -> List[str]:
        """Return ``-var key=value`` args for all registered TF variable overrides."""
        result: List[str] = []
        for key, value in self._tf_vars.items():
            result.extend(["-var", f"{key}={value}"])
        return result

    # ------------------------------------------------------------------
    # VM definition loading (parses main.tf)
    # ------------------------------------------------------------------

    def _load_vm_definitions(self, scenario: str) -> List[Dict[str, Any]]:
        """Parse ``main.tf`` and return the raw VM definition list.

        Variable references (e.g. ``${var.network_bridge}``) are returned as
        literal strings; subclasses may resolve them further.

        Raises:
            TerraformError: If main.tf is missing, unparseable, or lacks the
                            requested scenario.
        """
        main_tf = self.terraform_dir / "main.tf"
        if not main_tf.exists():
            raise TerraformError(
                f"main.tf not found at {main_tf}",
                details="Ensure terraform_dir points to the correct directory.",
            )

        try:
            with open(main_tf) as f:
                parsed = hcl2.load(f)
        except Exception as e:
            raise TerraformError(
                f"Failed to parse {main_tf.name} with python-hcl2",
                details=str(e),
            )

        # hcl2 returns locals as a list of dicts (one per locals block)
        locals_blocks = parsed.get("locals", [])
        vm_definitions: Dict[str, Any] = {}
        for block in locals_blocks:
            vm_definitions.update(block.get("vm_definitions", {}))

        if not vm_definitions:
            raise TerraformError(
                f"vm_definitions not found in any locals block of {main_tf.name}",
            )

        selected = vm_definitions.get(scenario)
        if not selected:
            raise TerraformError(
                f"No VM definitions for scenario='{scenario}'",
                details=f"Available scenarios: {list(vm_definitions.keys())}",
            )
        return selected

    # ------------------------------------------------------------------
    # Workspace management
    # ------------------------------------------------------------------

    def ensure_workspace(self, prefix: str, scenario: str) -> None:
        """Select the workspace ``env-<prefix>-<scenario>``, creating it if needed."""
        workspace = f"env-{prefix}-{scenario}"

        result = self._run(
            ["workspace", "select", workspace],
            check=False,
            capture=True,
        )
        if result.returncode == 0:
            logger.info(f"Selected workspace: {workspace}")
            return

        # Workspace does not exist — create it
        self._run(["workspace", "new", workspace])
        logger.info(f"Created workspace: {workspace}")

    # ------------------------------------------------------------------
    # Public lifecycle API — concrete
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Run ``terraform init``."""
        self._run(["init", "-input=false"])

    def read_outputs(self) -> TerraformOutputs:
        """Read current Terraform outputs from the active workspace."""
        result = self._run(["output", "-json"], capture=True)
        return TerraformOutputs.from_json(result.stdout)

    # ------------------------------------------------------------------
    # Public lifecycle API — abstract (provider-specific)
    # ------------------------------------------------------------------

    @abstractmethod
    def plan(self, config: Dict[str, Any]) -> None:
        """Generate tfvars, select workspace, and run ``terraform plan``."""

    @abstractmethod
    def apply(
        self, config: Dict[str, Any], *, auto_approve: bool = False
    ) -> TerraformOutputs:
        """Generate tfvars, select workspace, apply, and return outputs."""

    @abstractmethod
    def destroy(
        self, config: Dict[str, Any], *, auto_approve: bool = False
    ) -> None:
        """Select workspace and run ``terraform destroy``."""

    @abstractmethod
    def get_vm_definitions(
        self, config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Load and resolve VM definitions for the environment in *config*."""
