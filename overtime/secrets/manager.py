"""Secret manager with pluggable backends and prefix-based routing."""

import logging
import os
from typing import Optional

from .base import SecretBackend
from .backends.envvars import EnvVarsBackend
from .backends.dotenv import DotEnvBackend
from .backends.onepassword import OnePasswordBackend
from ..utils.exceptions import SecretError

logger = logging.getLogger(__name__)


class SecretManager:
    """
    Unified secret management with pluggable backends.

    Routing rules:
      - Keys starting with 'op://' → 1Password backend (auto-routed)
      - All other keys → configured default backend, then env var fallback

    Lookup chain for plain keys:
      1. Configured backend (dotenv or envvars)
      2. Environment variable (KEY uppercased, no prefix)
      3. Default value (or None)

    1Password is lazily initialized — if no op:// key is ever requested,
    the op CLI is never invoked and does not need to be installed.
    """

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize secret manager.

        Args:
            config: Secret configuration dictionary from provisioning spec.
                    Example: {'backend': 'dotenv', 'dotenv_path': '.env'}
        """
        config = config or {}
        backend_type = config.get('backend', 'dotenv')

        # Initialize default backend (for plain keys)
        if backend_type == 'envvars':
            self.default_backend: SecretBackend = EnvVarsBackend()
        elif backend_type == 'dotenv':
            self.default_backend = DotEnvBackend(config.get('dotenv_path'))
        else:
            raise SecretError(
                f"Unknown secret backend: {backend_type}",
                details="Supported backends: dotenv, envvars"
            )

        # 1Password backend is lazily initialized on first use
        self._onepassword: Optional[OnePasswordBackend] = None

        logger.info(f"Secret manager initialized. Default backend: {self.default_backend.backend_name()}")

    @property
    def onepassword(self) -> OnePasswordBackend:
        """Lazily initialize and return the 1Password backend."""
        if self._onepassword is None:
            self._onepassword = OnePasswordBackend()
        return self._onepassword

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get secret with routing and fallback.

        Routing:
          - op:// keys → 1Password
          - plain keys → default backend → env var → default value

        Args:
            key: Secret key name or op:// path
            default: Default value if not found anywhere

        Returns:
            Secret value or default
        """
        # Route op:// keys to 1Password
        if key.startswith('op://'):
            return self.onepassword.get_secret(key)

        # Try configured default backend
        value = self.default_backend.get_secret(key)
        if value is not None:
            return value

        # Fallback to environment variable (key uppercased, no prefix)
        env_value = os.environ.get(key.upper())
        if env_value is not None:
            logger.debug(f"Retrieved secret '{key}' from environment (fallback)")
            return env_value

        # Return default
        if default is not None:
            logger.debug(f"Using default value for secret '{key}'")

        return default

    def set(self, key: str, value: str) -> None:
        """
        Store secret in the default backend.

        Args:
            key: Secret key name
            value: Secret value

        Raises:
            NotImplementedError: If default backend is read-only
            SecretError: If key is an op:// path (managed in 1Password app)
        """
        if key.startswith('op://'):
            raise SecretError(
                "Cannot write to 1Password via this tool",
                details="Manage op:// secrets in the 1Password app"
            )
        self.default_backend.set_secret(key, value)

    def delete(self, key: str) -> None:
        """
        Delete secret from the default backend.

        Args:
            key: Secret key name

        Raises:
            NotImplementedError: If default backend is read-only
            SecretError: If key is an op:// path
        """
        if key.startswith('op://'):
            raise SecretError(
                "Cannot delete from 1Password via this tool",
                details="Manage op:// secrets in the 1Password app"
            )
        self.default_backend.delete_secret(key)

    def list(self) -> list[str]:
        """
        List secret keys in the default backend.

        Returns:
            List of secret key names
        """
        return self.default_backend.list_secrets()

    def backend_name(self) -> str:
        """Get default backend name for display."""
        return self.default_backend.backend_name()
