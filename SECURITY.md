# Security Policy

## Scope

OverTime is a homelab and educational tool designed to run on isolated networks
you control. It is **not** intended for production or enterprise environments.

By design, it:

- Disables Windows Firewall during AD domain setup
- Passes credentials via environment variables and Terraform variables
- Uses password-based WinRM for Windows VM configuration
- Stores secrets in a local `.env` file (when using the dotenv backend)
- Does not encrypt Terraform state files

These are deliberate trade-offs for a tool that automates disposable lab
environments. There is no running service, no network-facing API, and no
multi-user access model — you need direct access to the host and credentials
to use it at all.

## Reporting Issues

If you find a bug where secrets are leaked somewhere unexpected (logs, generated
files, git history), just
[open a regular issue](https://github.com/jacob-stout/OverTime/issues/new).


## What I Care About

- Secrets or credentials written to files that should be gitignored
- Credential leakage in logs or error output
- Injection in generated Terraform/Ansible configurations

## What Is Out of Scope

- The firewall-disable pattern (documented, intentional)
- Password-based auth for WinRM (required by Ansible for Windows)
- Lack of TLS certificate validation for Proxmox API (`pm_tls_insecure`)
- Terraform state not being encrypted (local-only by design)
