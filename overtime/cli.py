"""Command-line interface for OverTime."""

import logging

import sys
from pathlib import Path

import click

from .config.loader import load_provisioning_spec
from .utils.logging import setup_logging
from .utils.exceptions import OvertimeError
from .terraform.base import BaseOrchestrator
from .terraform.pve_orchestrator import PveOrchestrator
from .terraform.azure_orchestrator import AzureOrchestrator
from .terraform.azure_network_orchestrator import AzureNetworkOrchestrator
from .ansible.inventory import AnsibleInventoryGenerator
from .ansible.remote_runner import REMOTE_SSH_KEY_PATH

logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version='2.0.0')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--debug', is_flag=True, help='Enable debug logging')
@click.pass_context
def cli(ctx, verbose: bool, debug: bool):
    """
    OverTime - Multi-provider homelab infrastructure automation.

    Examples:
        overtime create config.yml
        overtime destroy config.yml
        overtime plan config.yml
    """
    ctx.ensure_object(dict)

    # Set up logging
    if debug:
        setup_logging('DEBUG', verbose=True)
    elif verbose:
        setup_logging('INFO', verbose=True)
    else:
        setup_logging('INFO', verbose=False)

    ctx.obj['verbose'] = verbose or debug
    ctx.obj['debug'] = debug


def _resolved_config(spec) -> dict:
    """Extract a plain, secrets-resolved config dict from a ProvisioningSpec.

    This is the dict that PveOrchestrator / AzureOrchestrator and
    AnsibleInventoryGenerator consume.  SecretStr fields are unwrapped here
    so the downstream modules never touch Pydantic.
    """
    config: dict = {
        "provider": spec.provider,
        "environment": {
            "environment_name_prefix": spec.environment.environment_name_prefix,
            "environment_fqdn":        spec.environment.environment_fqdn,
            "workspace":               spec.environment.workspace,
        },
        "vms": [
            {
                "name": vm.name,
                "os": vm.os,
                "role": vm.role,
                "cpu": vm.cpu,
                "memory": vm.memory,
                "disk": vm.disk,
                "ip_offset": vm.ip_offset,
            }
            for vm in spec.vms
        ],
        "ansible": {
            "ansible_user":     spec.ansible.ansible_user,
            "ansible_password": spec.ansible.ansible_password.get_secret_value(),
            "ssh_pub_key":      spec.ansible.ssh_pub_key,
            "ssh_key":          spec.ansible.ssh_key,
        },
    }

    if spec.proxmox is not None:
        config["proxmox"] = {
            "pm_api_url":            spec.proxmox.pm_api_url,
            "pm_user":               spec.proxmox.pm_user,
            "pm_password":           spec.proxmox.pm_password.get_secret_value() if spec.proxmox.pm_password else None,
            "pm_api_token":          spec.proxmox.pm_api_token.get_secret_value() if spec.proxmox.pm_api_token else None,
            "pm_tls_insecure":       spec.proxmox.pm_tls_insecure,
            "node_name":             spec.proxmox.node_name,
            "storage_pool":          spec.proxmox.storage_pool,
            "network_bridge":        spec.proxmox.network_bridge,
            "linux_template_id":     spec.proxmox.linux_template_id,
            "windows_template_id":   spec.proxmox.windows_template_id,
            "subnet_cidr":           spec.proxmox.subnet_cidr,
            "vm_gateway":            spec.proxmox.vm_gateway,
            "vm_id_start":           spec.proxmox.vm_id_start,
            "default_memory":        spec.proxmox.default_memory,
        }

    if spec.azure is not None:
        config["azure"] = {
            "subscription_id":    spec.azure.subscription_id,
            "resource_group":     spec.azure.resource_group,
            "location":           spec.azure.location,
            "vnet_name":          spec.azure.vnet_name,
            "vnet_cidr":          spec.azure.vnet_cidr,
            "subnet_cidr":        spec.azure.subnet_cidr,
            "default_vm_size":    spec.azure.default_vm_size,
            "admin_username":     spec.azure.admin_username,
            "allowed_source_prefix": spec.azure.allowed_source_prefix,
        }

    if spec.jumphost is not None:
        config["jumphost"] = {
            "ip":           spec.jumphost.ip,
        }

    if spec.configure is not None:
        config["configure"] = {
            "playbooks": [
                {
                    "playbook":     p.playbook,
                    "targets":      p.targets,
                    **({"description": p.description} if p.description else {}),
                }
                for p in spec.configure.playbooks
            ],
        }
    return config


def _make_orchestrator(config: dict) -> BaseOrchestrator:
    """Return the provider-appropriate orchestrator with env vars and TF vars."""
    if config["provider"] == "azure":
        orch = AzureOrchestrator()
        orch._extra_env["ARM_SUBSCRIPTION_ID"] = config["azure"]["subscription_id"]
    else:
        orch = PveOrchestrator()
        orch._tf_vars["ci_password"] = config["ansible"]["ansible_password"]
        proxmox = config["proxmox"]
        if proxmox.get("pm_api_token"):
            # BPG provider expects USER@REALM!TOKENID=UUID
            orch._extra_env["PROXMOX_VE_API_TOKEN"] = (
                f"{proxmox['pm_user']}={proxmox['pm_api_token']}"
            )
        else:
            orch._extra_env["PROXMOX_VE_PASSWORD"] = proxmox["pm_password"]
    return orch


@cli.command()
@click.argument('config_file', type=click.Path(exists=True, path_type=Path))
@click.option('--auto-approve', is_flag=True, help='Skip confirmation prompts')
@click.pass_context
def create(ctx, config_file: Path, auto_approve: bool):
    """Create infrastructure from configuration file."""
    try:
        # Load configuration
        spec = load_provisioning_spec(config_file)

        # Show summary
        click.echo(f"\nEnvironment: {spec.environment.environment_name_prefix}")
        click.echo(f"Provider: {spec.provider}")
        click.echo(f"VMs: {len(spec.vms)}")

        # Confirm
        if not auto_approve:
            click.confirm('\nProceed with creation?', abort=True)

        config = _resolved_config(spec)
        orchestrator = _make_orchestrator(config)
        orchestrator.init()
        outputs = orchestrator.apply(config, auto_approve=auto_approve)

        click.secho("\n✓ Infrastructure created", fg='green')
        click.echo(f"  Linux utility server IP: {outputs.jumphost_ip or 'N/A'}")
        if outputs.all_vm_ips:
            click.echo("\n  All VMs:")
            for name, ip in outputs.all_vm_ips.items():
                click.echo(f"    {name}: {ip}")

        # Connection hints for VMs with public IPs
        user = config["ansible"]["ansible_user"]
        lutil_pub = outputs.jumphost_public_ip
        wutil_pub = outputs.wutil_public_ip
        if lutil_pub or wutil_pub:
            click.echo("\n  Connect:")
            if lutil_pub:
                click.echo(f"    ssh {user}@{lutil_pub}")
            if wutil_pub:
                click.echo(f"    mstsc /v:{wutil_pub}  (RDP as {user})")

    except OvertimeError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.argument('config_file', type=click.Path(exists=True, path_type=Path))
@click.pass_context
def plan(ctx, config_file: Path):
    """Show Terraform execution plan."""
    try:
        spec = load_provisioning_spec(config_file)

        config = _resolved_config(spec)
        orchestrator = _make_orchestrator(config)
        orchestrator.init()
        orchestrator.plan(config)

    except OvertimeError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.argument('config_file', type=click.Path(exists=True, path_type=Path))
@click.option('--auto-approve', is_flag=True, help='Skip confirmation prompts')
@click.pass_context
def destroy(ctx, config_file: Path, auto_approve: bool):
    """Destroy infrastructure."""
    try:
        spec = load_provisioning_spec(config_file)

        # Confirm destruction
        if not auto_approve:
            click.secho(
                f"\n⚠️  WARNING: This will destroy environment "
                f"'{spec.environment.environment_name_prefix}' ({len(spec.vms)} VMs)",
                fg='red',
                bold=True
            )
            click.confirm('Are you sure?', abort=True)

        config = _resolved_config(spec)
        orchestrator = _make_orchestrator(config)
        orchestrator.init()
        orchestrator.destroy(config, auto_approve=auto_approve)

        click.secho("\n✓ Infrastructure destroyed", fg='green')

    except OvertimeError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.argument('config_file', type=click.Path(exists=True, path_type=Path))
@click.option('--dry-run', is_flag=True, help='Print the configure plan and exit without executing.')
@click.option('--keep-inventory', is_flag=True, help='Keep the local inventory file after configure (contains credentials).')
@click.pass_context
def configure(ctx, config_file: Path, dry_run: bool, keep_inventory: bool):
    """Configure an environment via its linux utility server.

    Reads the provisioning spec, connects to the linux utility server,
    bootstraps Ansible if needed, uploads the inventory and playbooks,
    runs readiness probes, then executes the playbook sequence from the spec.
    """
    try:
        spec   = load_provisioning_spec(config_file)
        config = _resolved_config(spec)
        orchestrator = _make_orchestrator(config)
        orchestrator.init()
        orchestrator.ensure_workspace(config["environment"]["workspace"])

        # ── 1. Resolve jumphost IP ──────────────────────────────────────
        jumphost_section = config.get("jumphost", {})
        jumphost_ip      = jumphost_section.get("ip")
        outputs          = None
        if not jumphost_ip:
            outputs     = orchestrator.read_outputs()
            jumphost_ip = outputs.jumphost_ip
            if not jumphost_ip:
                raise OvertimeError(
                    "No linux utility server IP in Terraform outputs and none specified in spec. "
                    "Set jumphost.ip in your provisioning spec or provision a linux utility server first."
                )
        # Strip CIDR suffix if present (Terraform outputs include it, e.g. "192.168.0.15/24")
        jumphost_ip = jumphost_ip.split("/")[0]
        click.echo(f"  linux utility server: {jumphost_ip}")

        # ── 2. Probe jumphost locally ───────────────────────────────────
        from .utils.probes import wait_for_vm
        click.echo("  Checking linux utility server reachability …")
        probe = wait_for_vm("jumphost", jumphost_ip, "linux", timeout=60)
        if not probe.reachable:
            raise OvertimeError(
                f"Cannot reach linux utility server at {jumphost_ip}. "
                "Check network connectivity and VM status."
            )
        click.secho(f"  linux utility server reachable in {probe.elapsed:.1f}s", fg="green")

        # ── 3. Build plan ───────────────────────────────────────────────
        vm_defs           = config["vms"]
        playbook_manifest = config.get("configure", {}).get("playbooks", [])

        from .ansible.configure_plan import build_configure_plan
        plan = build_configure_plan(vm_defs, playbook_manifest)

        # ── 4. Print plan ───────────────────────────────────────────────
        click.echo("\n  Configure plan:")
        for i, step in enumerate(plan, 1):
            click.echo(f"    {i}. [{step.targets:30s}] {step.description}")
            if step.extra_vars:
                click.echo(f"       extra vars: {step.extra_vars}")

        if dry_run:
            click.echo("\n  (dry-run — no changes made)")
            return

        if not click.confirm("\n  Proceed?"):
            return

        # ── 5. Generate inventory ───────────────────────────────────────
        if outputs is None:
            outputs = orchestrator.read_outputs()
        prefix  = config["environment"]["environment_name_prefix"]

        ssh_key_remote = (
            REMOTE_SSH_KEY_PATH if config["ansible"].get("ssh_key") else None
        )
        generator = AnsibleInventoryGenerator(
            outputs, vm_defs,
            name_prefix=prefix,
            fqdn=config["environment"]["environment_fqdn"],
            ansible_user=config["ansible"]["ansible_user"],
            ansible_password=config["ansible"]["ansible_password"],
            ssh_key_path=ssh_key_remote,
        )
        workspace = config["environment"]["workspace"]
        inventory_path = Path(f"{workspace}_ansible_inventory.yml")
        inventory_path.write_text(generator.to_yaml())
        click.secho(f"  Inventory written to {inventory_path}", fg="green")

        # ── 6. Connect + run ────────────────────────────────────────────
        from .ansible.remote_runner import RemoteRunner

        ssh_key  = config["ansible"].get("ssh_key")
        key_path = Path(ssh_key) if ssh_key else None
        if key_path and not key_path.exists():
            raise OvertimeError(
                f"SSH private key not found: {key_path}",
                details="Check the ssh_key path in your provisioning spec."
            )

        try:
            with RemoteRunner(
                host=jumphost_ip,
                username=config["ansible"]["ansible_user"],
                key_path=key_path,
                password=config["ansible"].get("ansible_password"),
            ) as runner:
                results = runner.run_plan(
                    plan,
                    inventory_path,
                    playbook_dir=Path("ansible"),
                    skip_missing=True,
                )

            # ── 7. Report ───────────────────────────────────────────────
            click.echo("\n  Results:")
            all_ok = True
            for r in results:
                status = "✓" if r.exit_code == 0 else "✗"
                color  = "green" if r.exit_code == 0 else "red"
                click.secho(f"    {status} {r.step.description} ({r.elapsed:.1f}s)", fg=color)
                if r.exit_code != 0:
                    all_ok = False
                    click.echo(f"\n      --- Output tail ---\n{r.stdout_tail}\n      --- end ---")

            if all_ok:
                click.secho("\n  Configuration complete.", fg="green")
            else:
                click.secho(
                    "\n  Configuration halted. Fix the error above and re-run: "
                    f"overtime configure {config_file}",
                    fg="red",
                )
                sys.exit(1)
        finally:
            if inventory_path.exists():
                if keep_inventory:
                    click.secho(
                        f"  Inventory kept at {inventory_path} (contains credentials)",
                        fg="yellow",
                    )
                else:
                    inventory_path.unlink()
                    logger.debug(f"Removed local inventory {inventory_path}")

    except OvertimeError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


@cli.command('validate')
@click.argument('config_file', type=click.Path(exists=True, path_type=Path))
def validate_config(config_file: Path):
    """Validate configuration file without executing."""
    try:
        spec = load_provisioning_spec(config_file)

        click.secho("✓ Configuration is valid", fg='green')
        click.echo(f"\nProvider: {spec.provider}")
        click.echo(f"Environment: {spec.environment.environment_name_prefix}")
        click.echo(f"VMs: {len(spec.vms)}")

    except OvertimeError as e:
        click.secho(f"✗ Configuration invalid", fg='red')
        click.echo(f"\n{e}")
        sys.exit(1)


# ─── Network command group (Azure shared infra) ─────────────────────────────

@cli.group()
def network():
    """Manage shared Azure network infrastructure (RG + VNet).

    Azure deployments require shared network infrastructure (Resource Group
    and Virtual Network) to be created before VMs.

    \b
    Workflow:
      overtime network create <spec>   # one-time: creates RG + VNet
      overtime create <spec>           # creates subnet + VMs
      overtime destroy <spec>          # destroys subnet + VMs
      overtime network destroy <spec>  # teardown: destroys RG + VNet
    """
    pass


@network.command('create')
@click.argument('config_file', type=click.Path(exists=True, path_type=Path))
@click.option('--auto-approve', is_flag=True, help='Skip confirmation prompts')
@click.pass_context
def network_create(ctx, config_file: Path, auto_approve: bool):
    """Create shared network infrastructure (Resource Group + VNet).

    Run this once before creating VMs with ``overtime create``.
    """
    try:
        spec = load_provisioning_spec(config_file)

        if spec.provider != "azure":
            raise OvertimeError("The 'network' command is only supported for the Azure provider.")

        config = _resolved_config(spec)

        click.echo(f"\nEnvironment: {spec.environment.environment_name_prefix}")
        click.echo(f"Resource Group: {spec.azure.resource_group}")
        click.echo(f"VNet: {spec.azure.vnet_name} ({spec.azure.vnet_cidr})")

        if not auto_approve:
            click.confirm('\nCreate shared network infrastructure?', abort=True)

        orchestrator = AzureNetworkOrchestrator()
        orchestrator.init()
        outputs = orchestrator.apply(config, auto_approve=auto_approve)

        click.secho("\n  Shared network created", fg='green')
        click.echo(f"    Resource Group: {outputs.get('resource_group_name') or 'N/A'}")
        click.echo(f"    VNet: {outputs.get('vnet_name') or 'N/A'}")

    except OvertimeError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


@network.command('plan')
@click.argument('config_file', type=click.Path(exists=True, path_type=Path))
@click.pass_context
def network_plan(ctx, config_file: Path):
    """Show Terraform plan for shared network infrastructure."""
    try:
        spec = load_provisioning_spec(config_file)

        if spec.provider != "azure":
            raise OvertimeError("The 'network' command is only supported for the Azure provider.")

        config = _resolved_config(spec)
        orchestrator = AzureNetworkOrchestrator()
        orchestrator.init()
        orchestrator.plan(config)

    except OvertimeError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


@network.command('destroy')
@click.argument('config_file', type=click.Path(exists=True, path_type=Path))
@click.option('--auto-approve', is_flag=True, help='Skip confirmation prompts')
@click.pass_context
def network_destroy(ctx, config_file: Path, auto_approve: bool):
    """Destroy shared network infrastructure (RG + VNet).

    Only run after all VMs have been destroyed.
    """
    try:
        spec = load_provisioning_spec(config_file)

        if spec.provider != "azure":
            raise OvertimeError("The 'network' command is only supported for the Azure provider.")

        if not auto_approve:
            click.secho(
                f"\n  WARNING: This will destroy the Resource Group "
                f"'{spec.azure.resource_group}' and VNet '{spec.azure.vnet_name}'. "
                f"Ensure all VMs are destroyed first.",
                fg='red', bold=True,
            )
            click.confirm('Are you sure?', abort=True)

        config = _resolved_config(spec)
        orchestrator = AzureNetworkOrchestrator()
        orchestrator.init()
        orchestrator.destroy(config, auto_approve=auto_approve)

        click.secho("\n  Shared network destroyed", fg='green')

    except OvertimeError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


@cli.command('scenarios')
@click.option('--provider', '-p',
              type=click.Choice(['proxmox', 'azure'], case_sensitive=False),
              default=None, help='Show scenario templates for a specific provider only.')
@click.option('--json', 'as_json', is_flag=True, help='Output as JSON.')
def scenarios_cmd(provider: str | None, as_json: bool):
    """List available scenario templates for each provider.

    Scenario templates are pre-built VM + playbook configurations that
    ``overtime setup`` can expand into a provisioning spec.  You can also
    write your own VM list from scratch.
    """
    from .scenarios import PROVIDER_SCENARIOS

    if as_json:
        import json as json_mod
        output = {}
        for prov, scens in PROVIDER_SCENARIOS.items():
            if provider and prov != provider:
                continue
            output[prov] = {
                name: {
                    "description": tmpl.description,
                    "vm_summary": tmpl.vm_summary,
                    "vms": tmpl.vms,
                    "default_playbooks": [
                        {"playbook": p.playbook, "targets": p.targets}
                        for p in tmpl.default_playbooks
                    ],
                }
                for name, tmpl in scens.items()
            }
        click.echo(json_mod.dumps(output, indent=2))
        return

    providers_to_show = (
        {provider: PROVIDER_SCENARIOS[provider]}
        if provider
        else PROVIDER_SCENARIOS
    )

    for prov, scens in providers_to_show.items():
        click.secho(f"\n  {prov}", fg='cyan', bold=True)
        click.echo(f"  {'=' * len(prov)}")

        for name, tmpl in scens.items():
            click.echo(f"\n    {name}")
            click.echo(f"      {tmpl.description}")
            click.echo(f"      {tmpl.vm_summary}")

            for vm in tmpl.vms:
                click.echo(f"        - {vm['name']:12s}  role={vm['role']:<8s}  os={vm['os']}")

            if tmpl.default_playbooks:
                click.echo("      Default playbooks:")
                for pb in tmpl.default_playbooks:
                    click.echo(f"        - {pb.playbook}  (targets: {pb.targets})")

    click.echo()


@cli.command('setup')
@click.argument('output_file', type=click.Path(), required=False, default=None)
def setup(output_file: str | None):
    """Interactively generate a starter provisioning spec YAML file.

    If OUTPUT_FILE is omitted, the file is written to
    configs/environments/<prefix>-provisioning-spec.yml
    so that .gitignore excludes it automatically.

    Optionally pick a scenario template to pre-populate the VM list and
    playbooks, or start with a blank spec and define VMs manually.
    """
    import yaml
    from .scenarios import get_scenarios_for_provider, default_playbooks_for

    # ── Provider ──────────────────────────────────────────────────────
    provider = click.prompt(
        "Provider",
        type=click.Choice(["proxmox", "azure"], case_sensitive=False),
        default="proxmox",
    )

    # ── Environment ───────────────────────────────────────────────────
    click.echo("\n-- Environment --")
    env_prefix = click.prompt("Environment name prefix (1-10 chars)", default="lab")
    env_fqdn = click.prompt("Environment FQDN", default="lab.local")

    # ── Scenario template (optional) ─────────────────────────────────
    provider_scenarios = get_scenarios_for_provider(provider)
    scenario_choices = sorted(provider_scenarios.keys())

    click.echo("\n-- Scenario Template --")
    click.echo("  Choose a scenario to pre-populate VMs and playbooks,")
    click.echo("  or choose 'custom' to start with an empty VM list.")
    scenario = click.prompt(
        "Scenario",
        type=click.Choice(scenario_choices + ["custom"], case_sensitive=False),
        default=scenario_choices[0],
    )

    # ── Provider-specific ─────────────────────────────────────────────
    spec: dict = {
        "provider": provider,
        "secrets": {"backend": "dotenv"},
    }

    if provider == "proxmox":
        click.echo("\n-- Proxmox --")
        use_token = click.confirm("Use API token instead of password?", default=True)
        proxmox_cfg: dict = {
            "pm_api_url": click.prompt(
                "Proxmox API URL", default="https://192.168.0.100:8006"
            ),
        }
        if use_token:
            proxmox_cfg["pm_user"] = click.prompt(
                "API token ID (user@realm!token-name)",
                default="overtime@pve!overtime-token",
            )
            proxmox_cfg["pm_api_token"] = "${secret:pm_api_token}"
        else:
            proxmox_cfg["pm_user"] = click.prompt("Proxmox user", default="root@pam")
            proxmox_cfg["pm_password"] = "${secret:pm_password}"
        proxmox_cfg.update({
            "pm_tls_insecure": click.confirm(
                "Skip TLS verification?", default=True
            ),
            "node_name": click.prompt("Node name", default="pve"),
            "storage_pool": click.prompt("Storage pool", default="local-lvm"),
            "network_bridge": click.prompt("Network bridge", default="vmbr0"),
            "linux_template_id": click.prompt("Linux template VM ID"),
            "windows_template_id": click.prompt("Windows template VM ID"),
            "subnet_cidr": click.prompt("Subnet CIDR", default="192.168.0.0/24"),
            "vm_gateway": click.prompt("VM gateway IP", default="192.168.0.1"),
            "vm_id_start": int(click.prompt("VM ID start", default="9000")),
            "default_memory": int(click.prompt("Default VM memory in MB", default="4096")),
        })
        spec["proxmox"] = proxmox_cfg
    else:
        click.echo("\n-- Azure --")
        spec["azure"] = {
            "subscription_id": click.prompt("Subscription ID (UUID)"),
            "resource_group": click.prompt("Resource group"),
            "location": click.prompt("Azure region", default="eastus"),
            "vnet_name": click.prompt("VNet name", default="ot-vnet"),
            "vnet_cidr": click.prompt("VNet CIDR", default="10.0.0.0/16"),
            "subnet_cidr": click.prompt("Subnet CIDR", default="10.0.1.0/24"),
            "default_vm_size": click.prompt("Default VM size", default="Standard_B2s"),
            "admin_username": click.prompt("Admin username", default="ot-bootstrap"),
            "allowed_source_prefix": click.prompt(
                "Allowed source IP/CIDR for NSG rules (your public IP recommended; '*' allows any internet source)",
                default="*",
            ),
        }

    # ── Workspace ─────────────────────────────────────────────────────
    if scenario != "custom":
        workspace = f"{env_prefix}-{scenario}"
    else:
        click.echo("\n-- Workspace --")
        click.echo("  Each spec needs a unique workspace name for Terraform state isolation.")
        workspace = click.prompt("Workspace name", default=env_prefix)

    # ── Resolve output path ────────────────────────────────────────────
    if output_file is None:
        env_dir = Path("configs/environments")
        env_dir.mkdir(parents=True, exist_ok=True)
        output_path = env_dir / f"{workspace}-provisioning-spec.yml"
    else:
        output_path = Path(output_file)

    if output_path.exists():
        click.confirm(
            f"\n  {output_path} already exists. Overwrite?", abort=True
        )

    # ── Environment section ───────────────────────────────────────────
    spec["environment"] = {
        "environment_name_prefix": env_prefix,
        "environment_fqdn": env_fqdn,
        "workspace": workspace,
    }

    # ── Ansible ───────────────────────────────────────────────────────
    click.echo("\n-- Ansible --")
    ansible_section: dict = {
        "ansible_user": click.prompt("Ansible user", default="ot-bootstrap"),
        "ansible_password": "${secret:ansible_password}",
        "ssh_pub_key": click.prompt(
            "SSH public key (leave blank if not using key auth)",
            default="",
        ),
    }

    if ansible_section["ssh_pub_key"]:
        ssh_key_path = click.prompt(
            "SSH private key path (required for key auth)",
            default="~/.ssh/id_ed25519",
        )
        ansible_section["ssh_key"] = ssh_key_path

    spec["ansible"] = ansible_section

    # ── VMs (from scenario template or empty) ─────────────────────────
    if scenario != "custom":
        tmpl = provider_scenarios[scenario]
        spec["vms"] = tmpl.vms
        playbooks = default_playbooks_for(provider, scenario)
        if playbooks:
            spec["configure"] = {"playbooks": playbooks}
    else:
        spec["vms"] = [
            {"name": "example-vm", "os": "linux", "role": "lutil", "cpu": 2, "disk": 32, "ip_offset": 10},
        ]

    # ── Write ─────────────────────────────────────────────────────────
    if provider == "azure":
        secret_lines = "#   az login\n"
    elif "pm_api_token" in spec.get("proxmox", {}):
        secret_lines = "#   export PM_API_TOKEN=...      # Proxmox API token\n"
    else:
        secret_lines = "#   export PM_PASSWORD=...        # Proxmox password\n"
    header = (
        "# OverTime provisioning spec — generated by `overtime setup`\n"
        "# Edit values below, then run:\n"
        f"{secret_lines}"
        "#   export ANSIBLE_PASSWORD=...\n"
        "#   overtime validate {file}\n"
        "#   overtime create   {file}\n\n"
    ).format(file=output_path.name)

    optional_sections = (
        "\n"
        "# Uncomment to override the jumphost IP (e.g. public IP or NAT IP).\n"
        "# By default, overtime configure resolves the IP from Terraform outputs.\n"
        "# jumphost:\n"
        "#   ip: 0.0.0.0\n"
    )

    with open(output_path, "w") as f:
        f.write(header)
        yaml.dump(spec, f, default_flow_style=False, sort_keys=False)
        f.write(optional_sections)

    # ── Next steps ────────────────────────────────────────────────────
    click.secho(f"\n  Spec written to {output_path}", fg="green")

    if scenario == "custom":
        click.echo("\n  Edit the 'vms' section to define your VMs, then:")
    else:
        click.echo(f"\n  Pre-populated with '{scenario}' template ({len(spec['vms'])} VMs).")
        click.echo("  Edit the 'vms' section to customize, then:")

    secrets_needed = ["ansible_password"]
    if provider == "proxmox":
        if "pm_api_token" in spec["proxmox"]:
            secrets_needed.insert(0, "pm_api_token")
        else:
            secrets_needed.insert(0, "pm_password")

    for key in secrets_needed:
        click.echo(f"    export {key.upper()}=<value>")

    click.echo(f"")
    click.echo(f"      overtime validate {output_path}")
    if provider == "azure":
        click.echo(f"      overtime network create {output_path}   # one-time: RG + VNet")
        click.echo(f"      overtime create {output_path}")
    else:
        click.echo(f"      overtime create {output_path}")


def main():
    """Entry point for CLI."""
    try:
        cli(obj={})
    except KeyboardInterrupt:
        click.echo("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception("Unexpected error")
        click.secho(f"\n✗ Unexpected error: {e}", fg='red')
        sys.exit(1)


if __name__ == '__main__':
    main()
