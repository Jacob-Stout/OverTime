"""1Password CLI secret backend."""

import logging
import shutil
import subprocess
from typing import Optional

from ..base import SecretBackend
from ...utils.exceptions import SecretError

logger = logging.getLogger(__name__)


class OnePasswordBackend(SecretBackend):
    """
    Read secrets from 1Password using the `op` CLI.

    Keys are full op:// paths as used by the CLI:
        op://vault/item/field

    Example:
        op://Dev/Proxmox/password

    This is a read-only backend. Secrets are managed in the 1Password app.
    The `op` CLI must be installed and the 1Password agent must be running.
    """

    OP_VERIFY_TIMEOUT = 10   # seconds — version check (no auth prompt)
    OP_READ_TIMEOUT = 60     # seconds — secret read (may trigger auth prompt)

    def __init__(self):
        """Initialize and verify op CLI is available."""
        self._op_path = self._resolve_op_path()
        self._verify_op_available()

    def _resolve_op_path(self) -> str:
        """Find the op binary, trying 'op' then 'op.exe' (WSL compatibility)."""
        for name in ('op', 'op.exe'):
            path = shutil.which(name)
            if path:
                logger.debug(f"Resolved 1Password CLI: {path}")
                return path
        raise SecretError(
            "1Password CLI (op) not found in PATH",
            details="Install from: https://1password.com/downloads/cli/"
        )

    def _verify_op_available(self) -> None:
        """Check that the op CLI is installed and reachable."""
        try:
            subprocess.run(
                [self._op_path, '--version'],
                capture_output=True,
                check=True,
                timeout=self.OP_VERIFY_TIMEOUT
            )
            logger.debug("1Password CLI (op) is available")
        except subprocess.TimeoutExpired:
            raise SecretError(
                "1Password CLI timed out during version check",
                details="Check that the 1Password agent is running"
            )

    def get_secret(self, key: str) -> Optional[str]:
        """
        Read a secret using op read.

        Args:
            key: Full op:// path (e.g. op://Dev/Proxmox/password)

        Returns:
            Secret value

        Raises:
            SecretError: If op read fails (not signed in, item not found, etc.)
        """
        try:
            result = subprocess.run(
                [self._op_path, 'read', key],
                capture_output=True,
                text=True,
                check=True,
                timeout=self.OP_READ_TIMEOUT
            )
            value = result.stdout.strip()
            logger.debug(f"Retrieved secret from 1Password: {key}")
            return value

        except subprocess.CalledProcessError as e:
            raise SecretError(
                f"1Password: failed to read {key}",
                details=e.stderr.strip() or "Unknown error"
            )
        except subprocess.TimeoutExpired:
            raise SecretError(
                f"1Password: timed out reading {key}",
                details="Check that the 1Password agent is running"
            )

    def set_secret(self, key: str, value: str) -> None:
        """Not supported — manage secrets in the 1Password app."""
        raise NotImplementedError(
            "1Password backend is read-only. "
            "Add or edit secrets in the 1Password app."
        )

    def delete_secret(self, key: str) -> None:
        """Not supported — manage secrets in the 1Password app."""
        raise NotImplementedError(
            "1Password backend is read-only. "
            "Delete secrets in the 1Password app."
        )

    def list_secrets(self) -> list[str]:
        """Not supported — use the 1Password app to browse secrets."""
        raise NotImplementedError(
            "1Password backend does not support listing. "
            "Use the 1Password app to browse your secrets."
        )

    def backend_name(self) -> str:
        """Backend name."""
        return "1Password"
