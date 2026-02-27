# Testing Guide

## Quick Start

```bash
# Install dev dependencies (from project root)
pip install -e ".[dev]"

# Run all tests
pytest

# Run all tests (explicit venv, useful on WSL where system python may lack packages)
./venv/bin/python -m pytest
```

## Test Configuration

Test settings live in `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
addopts = "-v --cov=overtime --cov-report=term-missing"
```

Coverage is enabled by default — every run prints a coverage report with missing lines.

## Project Structure

```
tests/
├── __init__.py
└── unit/
    ├── __init__.py
    ├── test_exceptions.py          # OvertimeError, ConfigurationError
    ├── test_config_loader.py       # YAML loading, Pydantic validation, secret resolution
    ├── test_scenarios.py           # Scenario registry, HCL sync, CLI scenarios command
    ├── test_secrets.py             # EnvVars, DotEnv, 1Password backends, SecretManager
    ├── test_base_orchestrator.py   # BaseOrchestrator ABC, subprocess, HCL parsing, workspace
    ├── test_terraform.py           # TerraformOutputs, PveOrchestrator, AnsibleInventoryGenerator
    ├── test_azure.py               # AzureOrchestrator, AzureConfig schema validation
    ├── test_azure_network.py       # AzureNetworkOrchestrator
    └── test_configure.py           # Probes, configure plan, remote runner, setup wizard
```

## What Each Test File Covers

| File | Production Module(s) | Key Tests |
|---|---|---|
| `test_exceptions.py` | `overtime/utils/exceptions.py` | Error messages, inheritance |
| `test_config_loader.py` | `overtime/config/loader.py`, `schema.py` | YAML parsing, Pydantic validation, HTTPS enforcement, IP validation |
| `test_scenarios.py` | `overtime/scenarios.py`, `overtime/cli.py` | Registry-HCL sync (catches drift), provider lookup, default playbooks, CLI `scenarios` command |
| `test_secrets.py` | `overtime/secrets/` (all backends + manager) | Set/get/delete, 1Password mocking, `${secret:key}` resolution, backend routing |
| `test_base_orchestrator.py` | `overtime/terraform/base.py` | ABC enforcement, `_run()` subprocess wrapper, HCL parsing, workspace select/create |
| `test_terraform.py` | `overtime/terraform/pve_orchestrator.py`, `state.py`, `overtime/ansible/inventory.py` | Terraform output parsing, tfvars writing (sensitive exclusion), plan/apply lifecycle, inventory generation (role grouping, k8s nesting) |
| `test_azure.py` | `overtime/terraform/azure_orchestrator.py`, `overtime/config/schema.py` | Azure tfvars, env setup, firewall disable, lifecycle, schema validation (UUID, reserved usernames) |
| `test_azure_network.py` | `overtime/terraform/azure_network_orchestrator.py` | Network workspace naming (`net-{prefix}`), tfvars, lifecycle |
| `test_configure.py` | `overtime/utils/probes.py`, `overtime/ansible/configure_plan.py`, `remote_runner.py`, `overtime/cli.py` | TCP probes, plan building (system steps, user steps), SSH bootstrap, upload, step execution, halt-on-failure, `setup` wizard CLI |

## Running Specific Tests

```bash
# Single file
pytest tests/unit/test_azure.py

# Single test class
pytest tests/unit/test_terraform.py::TestPveOrchestrator

# Single test
pytest tests/unit/test_scenarios.py::TestRegistryHclSync::test_proxmox_scenarios_match_hcl

# Keyword match
pytest -k "firewall"

# Stop on first failure
pytest -x

# Quiet output (dots only)
pytest -q
```

## Coverage

Coverage is collected automatically via `--cov=overtime` in `pyproject.toml`.

```bash
# Default coverage report (term-missing)
pytest

# HTML coverage report
pytest --cov-report=html
# Open htmlcov/index.html in a browser

# Fail if coverage drops below a threshold
pytest --cov-fail-under=75
```

## CI Pipeline Integration

All tests are pure unit tests — no external infrastructure, network access, or cloud credentials required. Every subprocess call (Terraform, SSH, `az` CLI, `op` CLI) is mocked.

Minimal CI job:

```yaml
# GitHub Actions example
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest --cov-fail-under=75
```

### Important: WSL-specific mocking

When running locally on WSL, `shutil.which()` can find Windows binaries (e.g., `az.cmd`, `op.exe`). Tests that mock `subprocess.run` must also mock `shutil.which` to avoid depending on host-installed tools. If you add new tests that check for CLI tool availability, mock both `subprocess.run` and `shutil.which`.

## Adding New Tests

1. Create or edit a file in `tests/unit/` matching the `test_*.py` pattern.
2. Mock all subprocess/SSH calls — tests must run without external tools.
3. If testing a module that checks for CLI tools via `shutil.which`, mock both `shutil.which` and `subprocess.run`.
4. Use `tmp_path` (pytest built-in) for any file I/O.
5. Run `pytest -x` to verify before committing.
