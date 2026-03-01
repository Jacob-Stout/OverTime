"""Abstract base class for Terraform orchestrators."""

import logging
import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List

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
    # Workspace management
    # ------------------------------------------------------------------

    def ensure_workspace(self, prefix: str) -> None:
        """Select the workspace ``env-<prefix>``, creating it if needed."""
        workspace = f"env-{prefix}"

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
