"""Environment variables secret backend."""

import os
import logging
from typing import Optional

from ..base import SecretBackend

logger = logging.getLogger(__name__)


class EnvVarsBackend(SecretBackend):
    """
    Read secrets from environment variables.

    Secret keys are prefixed with OVERTIME_SECRET_ when looking up env vars.
    Example: 'pm_password' → looks for OVERTIME_SECRET_PM_PASSWORD

    This is a read-only backend (set/delete not supported).
    """

    PREFIX = "OVERTIME_SECRET_"

    def get_secret(self, key: str) -> Optional[str]:
        """Get secret from environment variable."""
        env_var = f"{self.PREFIX}{key.upper()}"
        value = os.environ.get(env_var)

        if value:
            logger.debug(f"Retrieved secret '{key}' from environment")

        return value

    def set_secret(self, key: str, value: str) -> None:
        """Not supported for environment variables."""
        env_var = f"{self.PREFIX}{key.upper()}"
        raise NotImplementedError(
            f"EnvVarsBackend is read-only.\n"
            f"To set this secret, use: export {env_var}='value'"
        )

    def delete_secret(self, key: str) -> None:
        """Not supported for environment variables."""
        raise NotImplementedError("EnvVarsBackend is read-only")

    def list_secrets(self) -> list[str]:
        """List secrets from environment variables."""
        secrets = []
        for var in os.environ:
            if var.startswith(self.PREFIX):
                # Convert OVERTIME_SECRET_PM_PASSWORD → pm_password
                key = var[len(self.PREFIX):].lower()
                secrets.append(key)

        return sorted(secrets)

    def backend_name(self) -> str:
        """Backend name."""
        return "Environment Variables"
