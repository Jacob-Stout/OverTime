"""Scenario template library.

Scenarios are pre-built VM + playbook configurations that ``overtime setup``
can expand into a provisioning spec.  At runtime, OverTime only sees the flat
``vms`` list in the spec — it does not know or care whether the list came from
a scenario template or was hand-written.

Each provider has a dict mapping scenario names to ``ScenarioTemplate``
dataclasses.  The template carries the full VM list (the same format that
ends up in the YAML spec) and default playbooks.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class PlaybookDefault:
    """One entry in a scenario's suggested playbook list."""

    playbook: str
    targets: str


@dataclass(frozen=True)
class ScenarioTemplate:
    """A reusable scenario template for ``overtime setup``."""

    description: str
    vms: List[Dict[str, Any]]
    default_playbooks: List[PlaybookDefault] = field(default_factory=list)

    @property
    def vm_summary(self) -> str:
        """Human-readable summary of the VM topology."""
        win = sum(1 for v in self.vms if v["os"] == "windows")
        lin = sum(1 for v in self.vms if v["os"] == "linux")
        parts = []
        if win:
            parts.append(f"{win} Windows")
        if lin:
            parts.append(f"{lin} Linux")
        return f"{len(self.vms)} VMs ({', '.join(parts)})"


# ── Proxmox scenarios ────────────────────────────────────────────────────────

PROXMOX_SCENARIOS: Dict[str, ScenarioTemplate] = {
    "ad-lab-xs": ScenarioTemplate(
        description="Active Directory lab (extra-small): 1 DC, 1 util, 1 general",
        vms=[
            {"name": "ad-1a",    "role": "ad",      "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 10},
            {"name": "wutil-1a", "role": "wutil",   "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 20},
            {"name": "gen-1a",   "role": "general",  "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 30},
        ],
        default_playbooks=[
            PlaybookDefault("set_win_hostnames.yml", "ad,wutil,general"),
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "ad-lab-s": ScenarioTemplate(
        description="Active Directory lab (small): 1 DC, 1 util, 2 general",
        vms=[
            {"name": "ad-1a",    "role": "ad",      "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 10},
            {"name": "wutil-1a", "role": "wutil",   "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 20},
            {"name": "gen-1a",   "role": "general",  "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 30},
            {"name": "gen-1b",   "role": "general",  "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 31},
        ],
        default_playbooks=[
            PlaybookDefault("set_win_hostnames.yml", "ad,wutil,general"),
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "ad-lab-m": ScenarioTemplate(
        description="Active Directory lab (medium): 2 DCs, 1 util, 2 general",
        vms=[
            {"name": "ad-1a",    "role": "ad",      "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 10},
            {"name": "ad-2a",    "role": "ad",      "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 11},
            {"name": "wutil-1a", "role": "wutil",   "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 20},
            {"name": "gen-1a",   "role": "general",  "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 30},
            {"name": "gen-1b",   "role": "general",  "os": "windows", "cpu": 2, "disk": 40, "ip_offset": 31},
        ],
        default_playbooks=[
            PlaybookDefault("set_win_hostnames.yml", "ad,wutil,general"),
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("secondary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "k8s-dev": ScenarioTemplate(
        description="Kubernetes dev cluster: 3 control-plane, 2 workers",
        vms=[
            {"name": "k8s-1a", "role": "ctrl", "os": "linux", "cpu": 2, "disk": 32, "ip_offset": 40},
            {"name": "k8s-1b", "role": "ctrl", "os": "linux", "cpu": 2, "disk": 32, "ip_offset": 41},
            {"name": "k8s-1c", "role": "ctrl", "os": "linux", "cpu": 2, "disk": 32, "ip_offset": 42},
            {"name": "k8s-1d", "role": "work", "os": "linux", "cpu": 4, "disk": 32, "ip_offset": 43},
            {"name": "k8s-1e", "role": "work", "os": "linux", "cpu": 4, "disk": 32, "ip_offset": 44},
        ],
        default_playbooks=[
            PlaybookDefault("k8s_cluster_setup.yml", "k8s"),
        ],
    ),
    "jumphost": ScenarioTemplate(
        description="Shared linux utility server",
        vms=[
            {"name": "lutil-1a", "role": "lutil", "os": "linux", "cpu": 2, "disk": 32, "ip_offset": 15},
        ],
        default_playbooks=[
            PlaybookDefault("setup_jumphost.yml", "lutil"),
        ],
    ),
}

# ── Azure scenarios ──────────────────────────────────────────────────────────

AZURE_SCENARIOS: Dict[str, ScenarioTemplate] = {
    "ad-lab-xs": ScenarioTemplate(
        description="Active Directory lab (extra-small): 1 DC, 1 util, 1 general",
        vms=[
            {"name": "ad-1a",    "role": "ad",      "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 10},
            {"name": "wutil-1a", "role": "wutil",   "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 11},
            {"name": "gen-1a",   "role": "general",  "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 12},
        ],
        default_playbooks=[
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "ad-lab-s": ScenarioTemplate(
        description="Active Directory lab (small): 1 DC, 1 util, 2 general",
        vms=[
            {"name": "ad-1a",    "role": "ad",      "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 10},
            {"name": "wutil-1a", "role": "wutil",   "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 11},
            {"name": "gen-1a",   "role": "general",  "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 12},
            {"name": "gen-1b",   "role": "general",  "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 13},
        ],
        default_playbooks=[
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "ad-lab-m": ScenarioTemplate(
        description="Active Directory lab (medium): 2 DCs, 1 util, 2 general",
        vms=[
            {"name": "ad-1a",    "role": "ad",      "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 10},
            {"name": "ad-2a",    "role": "ad",      "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 11},
            {"name": "wutil-1a", "role": "wutil",   "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 12},
            {"name": "gen-1a",   "role": "general",  "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 13},
            {"name": "gen-1b",   "role": "general",  "os": "windows", "cpu": 2, "disk": 30, "ip_offset": 14},
        ],
        default_playbooks=[
            PlaybookDefault("primary_ad_setup.yml", "ad"),
            PlaybookDefault("secondary_ad_setup.yml", "ad"),
            PlaybookDefault("join_member_server.yml", "wutil,general"),
        ],
    ),
    "k8s-dev": ScenarioTemplate(
        description="Kubernetes dev cluster: 3 control-plane, 2 workers",
        vms=[
            {"name": "k8s-1a", "role": "ctrl", "os": "linux", "cpu": 2, "disk": 30, "ip_offset": 10},
            {"name": "k8s-1b", "role": "ctrl", "os": "linux", "cpu": 2, "disk": 30, "ip_offset": 11},
            {"name": "k8s-1c", "role": "ctrl", "os": "linux", "cpu": 2, "disk": 30, "ip_offset": 12},
            {"name": "k8s-1d", "role": "work", "os": "linux", "cpu": 2, "disk": 30, "ip_offset": 13},
            {"name": "k8s-1e", "role": "work", "os": "linux", "cpu": 2, "disk": 30, "ip_offset": 14},
        ],
        default_playbooks=[
            PlaybookDefault("k8s_cluster_setup.yml", "k8s"),
        ],
    ),
    "jumphost": ScenarioTemplate(
        description="Shared linux utility server",
        vms=[
            {"name": "lutil-1a", "role": "lutil", "os": "linux", "cpu": 2, "disk": 30, "ip_offset": 10},
        ],
        default_playbooks=[
            PlaybookDefault("setup_jumphost.yml", "lutil"),
        ],
    ),
}

# ── Unified lookup ───────────────────────────────────────────────────────────

PROVIDER_SCENARIOS: Dict[str, Dict[str, ScenarioTemplate]] = {
    "proxmox": PROXMOX_SCENARIOS,
    "azure": AZURE_SCENARIOS,
}


def get_scenarios_for_provider(provider: str) -> Dict[str, ScenarioTemplate]:
    """Return the scenario templates for a given provider.

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
    template = scenarios.get(scenario)
    if not template:
        return []
    return [
        {"playbook": p.playbook, "targets": p.targets}
        for p in template.default_playbooks
    ]
