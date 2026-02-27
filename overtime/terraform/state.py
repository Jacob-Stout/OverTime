"""Terraform state and output parsing."""

import json
import logging
from typing import Dict, Optional

from ..utils.exceptions import TerraformError

logger = logging.getLogger(__name__)


class TerraformOutputs:
    """Parsed Terraform outputs from ``terraform output -json``.

    The raw JSON shape is::

        { "<name>": { "value": <any>, "type": <type>, "sensitive": <bool> }, … }

    This class extracts the ``value`` for each output and exposes the three
    outputs that OverTime cares about as typed properties.
    """

    def __init__(self, raw: Dict):
        self._raw = raw

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_json(cls, json_str: str) -> "TerraformOutputs":
        """Parse the JSON string produced by ``terraform output -json``.

        Raises:
            TerraformError: If the string is not valid JSON or not a mapping.
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise TerraformError(
                "Failed to parse terraform output JSON",
                details=str(e),
            )

        if not isinstance(data, dict):
            raise TerraformError(
                "Terraform output JSON must be an object",
                details=f"Got: {type(data).__name__}",
            )
        return cls(data)

    # ------------------------------------------------------------------
    # Generic accessor
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[object]:
        """Return the *value* of a named output, or None if absent."""
        entry = self._raw.get(name)
        if entry is None:
            return None
        return entry.get("value")

    # ------------------------------------------------------------------
    # Typed properties
    # ------------------------------------------------------------------

    @property
    def jumphost_ip(self) -> Optional[str]:
        """IP of the linux utility server (with CIDR), or None if not deployed."""
        return self.get("jumphost_ip_address")

    @property
    def wutil_ip(self) -> Optional[str]:
        """IP of the Windows utility VM (public if available), or None."""
        return self.get("wutil_ip_address")

    @property
    def jumphost_public_ip(self) -> Optional[str]:
        """Public IP of the linux utility server, or None if not assigned."""
        return self.get("jumphost_public_ip")

    @property
    def wutil_public_ip(self) -> Optional[str]:
        """Public IP of the wutil VM, or None if not assigned."""
        return self.get("wutil_public_ip")

    @property
    def all_vm_ips(self) -> Dict[str, str]:
        """Map of VM name → IP with CIDR.  Empty dict if output is missing."""
        return self.get("all_vm_ips") or {}

    @property
    def all_vm_ids(self) -> Dict[str, int]:
        """Map of VM name → Proxmox VM ID.  Empty dict if output is missing."""
        return self.get("all_vm_ids") or {}
