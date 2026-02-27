"""Abstract base class for secret backends."""

from abc import ABC, abstractmethod
from typing import Optional


class SecretBackend(ABC):
    """Abstract interface for secret storage backends."""

    @abstractmethod
    def get_secret(self, key: str) -> Optional[str]:
        """
        Retrieve secret value by key.

        Args:
            key: Secret key name (or op:// path for 1Password)

        Returns:
            Secret value or None if not found
        """
        pass

    @abstractmethod
    def set_secret(self, key: str, value: str) -> None:
        """
        Store secret value.

        Args:
            key: Secret key name
            value: Secret value to store

        Raises:
            NotImplementedError: If backend is read-only
        """
        pass

    @abstractmethod
    def delete_secret(self, key: str) -> None:
        """
        Delete secret.

        Args:
            key: Secret key name

        Raises:
            NotImplementedError: If backend is read-only
        """
        pass

    @abstractmethod
    def list_secrets(self) -> list[str]:
        """
        List all secret keys (not values).

        Returns:
            List of secret key names

        Raises:
            NotImplementedError: If backend does not support listing
        """
        pass

    @abstractmethod
    def backend_name(self) -> str:
        """
        Human-readable backend name.

        Returns:
            Backend name for display
        """
        pass
