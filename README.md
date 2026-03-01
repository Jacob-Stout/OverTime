# OverTime

Multi-provider homelab infrastructure automation using Terraform and Ansible.

OverTime provisions VMs on **Proxmox VE** or **Azure**, then configures them with Ansible playbooks executed remotely on a Linux utility VM. It supports Active Directory labs, Kubernetes clusters, and standalone jump hosts.

> **Note:** OverTime is a personal learning and homelab tool. It is not designed
> for production or enterprise use. It disables firewalls, uses password-based
> authentication, and makes other trade-offs that prioritize convenience over
> defense-in-depth. Only use it on networks you control — Proxmox on a private
> VLAN, or Azure with NSG rules locked to your IP.

## Prerequisites

- Python >= 3.10
- Terraform >= 1.9
- A Proxmox VE hypervisor with golden VM templates (Linux with [cloud-init](https://cloud-init.io/), Windows with [Cloudbase-Init](https://cloudbase.it/cloudbase-init/)), **or** an Azure subscription
- (Azure) Azure CLI (`az`) — used for authentication and post-deploy tasks
- (Optional) 1Password CLI (`op`) for secret management

## Installation

### Linux / macOS / WSL

```bash
git clone https://github.com/Jacob-Stout/OverTime.git && cd OverTime
python -m venv venv
source venv/bin/activate
pip install -e .          # installs the overtime CLI
pip install -e ".[dev]"   # optional: also installs pytest, ruff, black, mypy
```

### Windows (PowerShell)

```powershell
git clone https://github.com/Jacob-Stout/OverTime.git; cd OverTime
python -m venv venv
venv\Scripts\Activate.ps1
pip install -e .
pip install -e ".[dev]"   # optional: dev dependencies
```

> If you get an execution policy error, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force` first.

## Quick Start

### 1. Generate a provisioning spec

The setup wizard walks you through provider, environment, and connection details:

```bash
overtime setup my-lab.yml
```

Or copy an example and edit manually:

```bash
cp configs/environments/example-proxmox.yml my-lab.yml   # Proxmox
cp configs/environments/example-azure.yml my-lab.yml      # Azure
```

### 2. Set secrets

Secrets referenced as `${secret:key}` in your spec are resolved at load time. You can provide them via a `.env` file or environment variables.

**Option A: `.env` file (recommended)**

Copy the example and fill in your values:

```bash
cp .env.example .env
```

**Option B: Environment variables**

Linux / macOS / WSL:

```bash
export PM_PASSWORD=...         # Proxmox only
export ANSIBLE_PASSWORD=...
```

Windows (PowerShell):

```powershell
$env:PM_PASSWORD = "..."         # Proxmox only
$env:ANSIBLE_PASSWORD = "..."
```

> Environment variables always work as a fallback regardless of which `secrets.backend` is configured.

### 3. Validate, create, and configure

```bash
overtime validate my-lab.yml             # check config
overtime plan my-lab.yml                 # show Terraform execution plan

# Azure only: create shared network first (one-time per environment)
overtime network create my-lab.yml       # create Resource Group + VNet

overtime create my-lab.yml               # provision VMs with Terraform
overtime configure my-lab.yml            # configure VMs with Ansible (via SSH on linux utility VM)
overtime destroy my-lab.yml              # tear down VMs

# Azure only: tear down shared network after all VMs destroyed
overtime network destroy my-lab.yml
```

## Provisioning Spec Format

You define your VMs directly in the spec. Use `overtime setup` to generate a spec from a scenario template, or write one from scratch:

```yaml
provider: proxmox  # or azure

secrets:
  backend: dotenv              # "dotenv" (default) or "envvars"; env vars always work as fallback

proxmox:
  pm_api_url: "https://192.168.0.100:8006"
  pm_user: "terraform@pve"
  pm_password: "${secret:pm_password}"
  # ... see configs/environments/example-proxmox.yml for all fields

environment:
  environment_name_prefix: "lab"
  environment_fqdn: "lab.local"

ansible:
  ansible_user: "ot-bootstrap"
  ansible_password: "${secret:ansible_password}"
  ssh_pub_key: "ssh-ed25519 AAAA..."

vms:
  - name: dc-1
    os: windows
    role: ad
    cpu: 2
    disk: 40
    ip_offset: 10
  - name: jumpbox
    os: linux
    role: lutil
    cpu: 2
    disk: 32
    ip_offset: 15

configure:                          # optional: playbook sequence for `overtime configure`
  playbooks:
    - playbook: "primary_ad_setup.yml"
      targets: "ad"
```

See [example-proxmox.yml](configs/environments/example-proxmox.yml) and [example-azure.yml](configs/environments/example-azure.yml) for complete references with all fields and comments.

## Scenario Templates

`overtime setup` can pre-populate your spec from built-in scenario templates. List them with `overtime scenarios`:

| Template | VMs | Description |
|---|---|---|
| `ad-lab-xs` | 3 Windows | 1 AD controller, 1 util, 1 general |
| `ad-lab-s` | 4 Windows | 1 AD controller, 1 util, 2 general |
| `ad-lab-m` | 5 Windows | 2 AD controllers, 1 util, 2 general |
| `k8s-dev` | 5 Linux | 3 K8s control-plane, 2 workers |
| `jumphost` | 1 Linux | Shared linux utility server / jump host |

Templates are starting points — once written to your spec, you can add, remove, or modify VMs freely.

## Two-Phase Workflow

OverTime separates infrastructure provisioning from configuration:

0. **(Azure only) `overtime network create`** creates the shared Resource Group and Virtual Network. Run once per environment.
1. **`overtime create`** runs Terraform to provision VMs. No SSH, no Ansible.
2. **`overtime configure`** SSHes to the linux utility server / jump host, bootstraps Ansible, uploads playbooks and inventory, then executes the playbook sequence defined in your spec.

This means you can `create` once and `configure` repeatedly as you iterate on playbooks.

## Secret Management

Secrets referenced as `${secret:key}` in specs are resolved at load time and never written to Terraform state files.

| Method | How | Use Case |
|---|---|---|
| `.env` file (default) | Copy `.env.example` to `.env`, fill in values | Persistent local convenience |
| Environment variables | `export KEY=...` (bash) or `$env:KEY = "..."` (PowerShell) | Works everywhere, nothing on disk |
| 1Password (`op://` prefix) | `${secret:op://Vault/Item/field}` | Secret sharing via `op` CLI |

Set `secrets.backend` in your spec to `dotenv` (reads from `.env` file, default) or `envvars` (reads from environment only). Environment variables always work as a fallback regardless of backend.

## Development

```bash
pip install -e ".[dev]"

# Run tests
pytest

# Run a specific test file
pytest tests/unit/test_secrets.py -v

# Lint and format
ruff check overtime/
black overtime/
```

## License

This project is licensed under the MIT License.
