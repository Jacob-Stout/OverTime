"""Per-provider scenario registry.

Each provider has a dict mapping scenario names to ScenarioInfo dataclasses.
This module is the single source of truth for:
  - which scenarios each provider supports
  - human-readable descriptions
  - default playbook suggestions for ``overtime setup``

The actual VM topology (how many VMs, what roles, what IPs) lives in the
Terraform HCL files.  A sync test in tests/unit/test_scenarios.py verifies
that every key in the HCL vm_definitions also appears in this registry, and
vice versa.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class PlaybookDefault:
    """One entry in a scenario's suggested playbook list."""

    playbook: str
    targets: str


@dataclass(frozen=True)
class ScenarioInfo:
    """Metadata about a single scenario."""

    description: str
    vm_summary: str
    default_playbooks: List[PlaybookDefault] = field(default_factory=list)


# ── Proxmox scenarios ────────────────────────────────────────────────────────

PROXMOX_SCENARIOS: Dict[str, ScenarioInfo] = {
    "ad-lab-xs": ScenarioInfo(
        description="Active Directory lab (extra-small): 1 DC, 1 util, 1 general",
        vm_summary="3 Windows VMs",
        default_playbooks=[
            PlaybookDefault("set_win_hostnames.yml", "ad,wutil,general"),
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "ad-lab-s": ScenarioInfo(
        description="Active Directory lab (small): 1 DC, 1 util, 2 general",
        vm_summary="4 Windows VMs",
        default_playbooks=[
            PlaybookDefault("set_win_hostnames.yml", "ad,wutil,general"),
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "ad-lab-m": ScenarioInfo(
        description="Active Directory lab (medium): 2 DCs, 1 util, 2 general",
        vm_summary="5 Windows VMs",
        default_playbooks=[
            PlaybookDefault("set_win_hostnames.yml", "ad,wutil,general"),
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("secondary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "k8s-dev": ScenarioInfo(
        description="Kubernetes dev cluster: 3 control-plane, 2 workers",
        vm_summary="5 Linux VMs",
        default_playbooks=[
            PlaybookDefault("k8s_cluster_setup.yml", "k8s"),
        ],
    ),
    "jumphost": ScenarioInfo(
        description="Shared linux utility server",
        vm_summary="1 Linux VM",
        default_playbooks=[
            PlaybookDefault("setup_jumphost.yml", "lutil"),
        ],
    ),
}

# ── Azure scenarios ──────────────────────────────────────────────────────────

AZURE_SCENARIOS: Dict[str, ScenarioInfo] = {
    "ad-lab-xs": ScenarioInfo(
        description="Active Directory lab (extra-small): 1 DC, 1 util, 1 general",
        vm_summary="3 Windows VMs",
        default_playbooks=[
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "ad-lab-s": ScenarioInfo(
        description="Active Directory lab (small): 1 DC, 1 util, 2 general",
        vm_summary="4 Windows VMs",
        default_playbooks=[
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "ad-lab-m": ScenarioInfo(
        description="Active Directory lab (medium): 2 DCs, 1 util, 2 general",
        vm_summary="5 Windows VMs",
        default_playbooks=[
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("secondary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "k8s-dev": ScenarioInfo(
        description="Kubernetes dev cluster: 3 control-plane, 2 workers",
        vm_summary="5 Linux VMs",
        default_playbooks=[
            PlaybookDefault("k8s_cluster_setup.yml", "k8s"),
        ],
    ),
    "jumphost": ScenarioInfo(
        description="Shared linux utility server",
        vm_summary="1 Linux VM",
        default_playbooks=[
            PlaybookDefault("setup_jumphost.yml", "lutil"),
        ],
    ),
}

# ── Unified lookup ───────────────────────────────────────────────────────────

PROVIDER_SCENARIOS: Dict[str, Dict[str, ScenarioInfo]] = {
    "proxmox": PROXMOX_SCENARIOS,
    "azure": AZURE_SCENARIOS,
}


def get_scenarios_for_provider(provider: str) -> Dict[str, ScenarioInfo]:
    """Return the scenario registry for a given provider.

    Raises KeyError if the provider is unknown.
    """
    return PROVIDER_SCENARIOS[provider]


def default_playbooks_for(provider: str, scenario: str) -> List[Dict[str, Any]]:
    """Return the default playbook manifest dicts for setup wizard output.

    Returns a list of dicts with ``playbook`` and ``targets`` keys, matching
    the format expected by the ``configure.playbooks`` spec section.
    Returns an empty list for unknown provider/scenario combinations.
    """
    scenarios = PROVIDER_SCENARIOS.get(provider, {})
    info = scenarios.get(scenario)
    if not info:
        return []
    return [
        {"playbook": p.playbook, "targets": p.targets}
        for p in info.default_playbooks
    ]


def scenario_keys_from_hcl(main_tf_path: Path) -> set:
    """Parse a Terraform main.tf and return the set of vm_definitions keys.

    Used by the sync test to verify the registry matches the HCL.
    """
    import hcl2

    with open(main_tf_path) as f:
        parsed = hcl2.load(f)

    vm_definitions: Dict[str, Any] = {}
    for block in parsed.get("locals", []):
        vm_definitions.update(block.get("vm_definitions", {}))
    return set(vm_definitions.keys())
