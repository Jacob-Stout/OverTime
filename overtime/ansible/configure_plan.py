"""Build an ordered configure plan from the provisioning spec.

The plan is a list of PlaybookStep objects.  System steps are prepended
automatically unless the operator already listed them in the manifest:

    1. ``setup_jumphost.yml``  → lutil     (if lutil is in the topology)
    2. ``probe_targets.yml``   → all:!lutil (if non-lutil VMs exist)

Everything after that is read verbatim from ``configure.playbooks`` in the
provisioning spec.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class PlaybookStep:
    """One step in a configure plan."""
    playbook:    str                          # filename, relative to the playbook dir
    targets:     str                          # Ansible host pattern for --limit
    description: str                          # human-readable label for CLI output
    extra_vars:  Dict[str, Any] = field(default_factory=dict)


def build_configure_plan(
    vm_definitions:   List[Dict[str, Any]],   # from the orchestrator (each has ``role``)
    playbook_manifest: List[Dict[str, str]],  # spec["configure"]["playbooks"]
) -> List[PlaybookStep]:
    """Produce the ordered playbook plan.

    Args:
        vm_definitions:    VM dicts.  Used only to check whether a linux utility
                           server is in the topology (determines whether
                           setup_jumphost.yml is prepended).
        playbook_manifest: The ``configure.playbooks`` list from the spec.
                           Each entry has ``playbook`` and ``targets`` keys.
                           An optional ``description`` key overrides the
                           default (which is the playbook filename).

    Returns:
        Ordered list of PlaybookStep.
    """
    roles = [vm["role"] for vm in vm_definitions]
    manifest_playbooks = {e["playbook"] for e in playbook_manifest}
    plan: List[PlaybookStep] = []

    # ── System steps (prepended unless already in manifest) ───────────
    if "lutil" in roles and "setup_jumphost.yml" not in manifest_playbooks:
        plan.append(PlaybookStep(
            playbook    = "setup_jumphost.yml",
            targets     = "lutil",
            description = "Configure linux utility server as Ansible control node",
        ))

    non_lutil_roles = [r for r in roles if r != "lutil"]
    if non_lutil_roles and "probe_targets.yml" not in manifest_playbooks:
        plan.append(PlaybookStep(
            playbook    = "probe_targets.yml",
            targets     = "all:!lutil",
            description = "Wait for target VMs to become reachable",
        ))

    # ── User-specified playbooks (verbatim from spec) ──────────────────
    for entry in playbook_manifest:
        plan.append(PlaybookStep(
            playbook    = entry["playbook"],
            targets     = entry["targets"],
            description = entry.get("description", entry["playbook"]),
        ))

    return plan
