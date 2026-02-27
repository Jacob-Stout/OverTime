"""Configuration file loading and validation."""

import logging
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import ValidationError

from .schema import ProvisioningSpec
from ..utils.exceptions import ConfigurationError
from ..secrets.manager import SecretManager

logger = logging.getLogger(__name__)


def load_yaml(config_file: Path) -> Dict[str, Any]:
    """
    Load YAML configuration file.

    Args:
        config_file: Path to YAML configuration file

    Returns:
        Dictionary of configuration data

    Raises:
        ConfigurationError: If file doesn't exist or YAML is invalid
    """
    if not config_file.exists():
        raise ConfigurationError(
            f"Configuration file not found: {config_file}",
            details="Check the file path and try again."
        )

    try:
        with open(config_file) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ConfigurationError(
                "Configuration file must contain a YAML dictionary",
                details=f"Got: {type(data)}"
            )

        logger.debug(f"Loaded configuration from {config_file}")
        return data

    except yaml.YAMLError as e:
        raise ConfigurationError(
            f"Invalid YAML syntax in {config_file}",
            details=str(e)
        )


def _resolve_secrets(data: Any, manager: SecretManager) -> Any:
    """
    Recursively resolve ${secret:key} references in configuration.

    Supports plain keys (resolved via default backend + env var fallback)
    and op:// paths (resolved via 1Password).

    Examples:
        ${secret:pm_password}                  → reads from .env
        ${secret:op://Dev/Proxmox/password}    → reads from 1Password

    Args:
        data: Configuration data (dict, list, or scalar)
        manager: SecretManager instance

    Returns:
        Configuration with all secret references replaced

    Raises:
        ConfigurationError: If a referenced secret is not found
    """
    if isinstance(data, dict):
        return {k: _resolve_secrets(v, manager) for k, v in data.items()}

    elif isinstance(data, list):
        return [_resolve_secrets(item, manager) for item in data]

    elif isinstance(data, str) and data.startswith('${secret:') and data.endswith('}'):
        # Extract key: ${secret:pm_password}              → pm_password
        #              ${secret:op://Dev/X/password}      → op://Dev/X/password
        key = data[9:-1]
        value = manager.get(key)

        if value is None:
            raise ConfigurationError(
                f"Secret not found: {key}",
                details=f"Referenced in configuration as: {data}"
            )

        logger.debug(f"Resolved secret reference: {key}")
        return value

    else:
        return data


def load_provisioning_spec(config_file: Path) -> ProvisioningSpec:
    """
    Load and validate provisioning specification.

    Secret references (${secret:key}) are resolved before validation.

    Args:
        config_file: Path to provisioning spec YAML file

    Returns:
        Validated ProvisioningSpec object

    Raises:
        ConfigurationError: If validation fails or secrets are missing
    """
    logger.info(f"Loading configuration: {config_file}")

    # Load YAML
    raw_data = load_yaml(config_file)

    # Initialize secret manager from config (secrets block is optional)
    secret_config = raw_data.get('secrets', {})
    manager = SecretManager(secret_config)

    # Resolve ${secret:...} references before Pydantic sees the data
    resolved_data = _resolve_secrets(raw_data, manager)

    logger.info(f"✓ Resolved secrets from {manager.backend_name()}")

    # Validate with Pydantic
    try:
        spec = ProvisioningSpec.model_validate(resolved_data)
        logger.info("✓ Configuration valid")
        return spec

    except ValidationError as e:
        # Format validation errors nicely
        errors = []
        for error in e.errors():
            field = '.'.join(str(loc) for loc in error['loc'])
            message = error['msg']
            errors.append(f"  - {field}: {message}")

        raise ConfigurationError(
            "Configuration validation failed",
            details="\n".join(errors)
        )
