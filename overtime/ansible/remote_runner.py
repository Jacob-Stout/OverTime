"""SSH to the linux utility server and execute an Ansible playbook plan.

Uses Paramiko (already a project dependency) for SSH.  The runner:

    1. Bootstraps Ansible on the linux utility server if not already installed.
    2. Uploads the generated inventory file.
    3. Uploads the playbook directory.
    4. Executes each PlaybookStep in order.
    5. Returns a StepResult per step (exit code, stdout tail, elapsed time).

``setup_jumphost.yml`` is special-cased: it runs with ``--connection local``
and no inventory, because it configures the linux utility server itself.

If any step exits non-zero the runner stops and returns.  The caller
decides whether to retry or report the failure.
"""

import logging
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import paramiko

from .configure_plan import PlaybookStep
from ..utils.exceptions import OvertimeError

logger = logging.getLogger(__name__)

_DEFAULT_REMOTE_DIR = "overtime"
REMOTE_SSH_KEY_PATH = "~/.ssh/ot_key"


class RemoteRunError(OvertimeError):
    """A playbook step exited non-zero on the linux utility server."""


@dataclass
class StepResult:
    """Outcome of one playbook step executed on the linux utility server."""
    step:        PlaybookStep
    exit_code:   int
    stdout_tail: str     # last 50 lines of combined stdout + stderr
    elapsed:     float   # seconds


class RemoteRunner:
    """SSH-based playbook executor targeting the linux utility server.

    Args:
        host:     Linux utility server IP or hostname.
        username: SSH username.
        key_path: Path to the SSH private key (PEM).  Optional.
        password: SSH password (fallback if key auth fails).  Optional.
    """

    def __init__(
        self,
        host: str,
        username: str,
        *,
        key_path:  Optional[Path] = None,
        password:  Optional[str]  = None,
    ):
        self.host     = host
        self.username = username
        self.key_path = key_path
        self.password = password
        self._remote_base = f"/home/{username}/{_DEFAULT_REMOTE_DIR}"
        self._client: Optional[paramiko.SSHClient] = None

    # ─── Connection ─────────────────────────────────────────────────────

    def connect(self) -> None:
        """Open SSH connection to the linux utility server."""
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict = {
            "hostname":  self.host,
            "username":  self.username,
            "timeout":   30,
        }
        if self.key_path:
            kwargs["key_filename"] = str(self.key_path)
        if self.password:
            kwargs["password"] = self.password
        self._client.connect(**kwargs)
        logger.info(f"Connected to linux utility server at {self.host}")

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    # ─── Bootstrap ──────────────────────────────────────────────────────

    def bootstrap_ansible(self) -> None:
        """Ensure Ansible is installed on the linux utility server.

        Uses the Ansible PPA for a stable, up-to-date package.  Idempotent:
        does nothing if ``ansible`` is already on PATH.

        Raises:
            RemoteRunError: If the install command exits non-zero.
        """
        _, stdout, _ = self._client.exec_command("which ansible")
        if stdout.channel.recv_exit_status() == 0:
            logger.info("Ansible already installed on linux utility server")
            return

        logger.info("Bootstrapping Ansible on linux utility server …")
        install_cmd = (
            "sudo apt-get update -qq && "
            "sudo apt-get install -y -qq software-properties-common && "
            "sudo add-apt-repository -y ppa:ansible/ansible && "
            "sudo apt-get update -qq && "
            "sudo apt-get install -y -qq ansible"
        )
        _, stdout, stderr = self._client.exec_command(install_cmd, timeout=600)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            err = stderr.read().decode("utf-8", errors="replace")[-500:]
            raise RemoteRunError(
                f"Ansible install failed on linux utility server (exit {exit_code})",
                details=err,
            )
        logger.info("Ansible installed on linux utility server")

    # ─── Upload ─────────────────────────────────────────────────────────

    def _sftp(self) -> paramiko.SFTPClient:
        return self._client.open_sftp()

    def _ensure_dir(self, remote_path: str) -> None:
        """mkdir -p on the remote."""
        self._client.exec_command(f"mkdir -p {shlex.quote(remote_path)}")

    def upload_inventory(self, local_path: Path) -> str:
        """Upload the inventory file; return the remote path."""
        remote_dir  = f"{self._remote_base}/inventory"
        remote_path = f"{remote_dir}/{local_path.name}"
        self._ensure_dir(remote_dir)
        with self._sftp() as sftp:
            sftp.put(str(local_path), remote_path)
        logger.info(f"Uploaded inventory → {remote_path}")
        return remote_path

    def upload_playbooks(self, local_playbook_dir: Path) -> str:
        """Upload all .yml files from the local playbook directory; return remote dir."""
        remote_dir = f"{self._remote_base}/playbooks"
        self._ensure_dir(remote_dir)
        with self._sftp() as sftp:
            for yml in sorted(local_playbook_dir.glob("*.yml")):
                sftp.put(str(yml), f"{remote_dir}/{yml.name}")
        logger.info(f"Uploaded playbooks → {remote_dir}")
        return remote_dir

    def upload_ssh_key(self, local_path: Path) -> None:
        """Upload the SSH private key to the linux utility server.

        Places the key at ``~/.ssh/ot_key`` (0600) so Ansible can use it
        to authenticate against managed VMs that have password auth disabled.
        Idempotent — overwrites silently if already present.

        Note: SFTP does not expand ``~``, so we resolve ``$HOME`` via a shell
        command first and use the absolute path for the SFTP put.
        """
        _, stdout, _ = self._client.exec_command("echo $HOME")
        home = stdout.read().decode().strip()
        remote_key_path = f"{home}/.ssh/ot_key"

        _, mk_stdout, _ = self._client.exec_command(
            f"mkdir -p {home}/.ssh && chmod 700 {home}/.ssh"
        )
        mk_stdout.channel.recv_exit_status()  # wait before opening SFTP

        with self._sftp() as sftp:
            sftp.put(str(local_path), remote_key_path)
        self._client.exec_command(f"chmod 600 {remote_key_path}")
        logger.info(f"Uploaded SSH key → {remote_key_path}")

    # ─── Execute ────────────────────────────────────────────────────────

    def _run_command(self, cmd: str, timeout: int = 3600):
        """Run a command on the linux utility server.  Returns (exit_code, tail, elapsed)."""
        logger.info(f"[jumphost] {cmd}")
        start = time.monotonic()
        _, stdout, stderr = self._client.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        elapsed   = time.monotonic() - start

        out_lines = stdout.read().decode("utf-8", errors="replace").splitlines()
        err_lines = stderr.read().decode("utf-8", errors="replace").splitlines()
        tail = "\n".join((out_lines + err_lines)[-50:])
        return exit_code, tail, elapsed

    def run_step(
        self,
        step: PlaybookStep,
        inventory_remote: str,
        playbook_remote_dir: str,
    ) -> StepResult:
        """Execute one PlaybookStep using the uploaded inventory."""
        playbook_path = f"{playbook_remote_dir}/{step.playbook}"

        cmd_parts = ["ansible-playbook", "-i", shlex.quote(inventory_remote), shlex.quote(playbook_path)]
        if step.targets:
            cmd_parts.extend(["--limit", shlex.quote(step.targets)])
        for key, val in step.extra_vars.items():
            cmd_parts.extend(["-e", shlex.quote(f"{key}={val}")])

        exit_code, tail, elapsed = self._run_command(" ".join(cmd_parts))
        result = StepResult(step=step, exit_code=exit_code, stdout_tail=tail, elapsed=elapsed)

        if exit_code != 0:
            logger.warning(f"  '{step.description}' exited {exit_code}")
        else:
            logger.info(f"  '{step.description}' completed in {elapsed:.1f}s")
        return result

    def _run_setup_jumphost(
        self,
        step: PlaybookStep,
        playbook_remote_dir: str,
    ) -> StepResult:
        """Special-case: setup_jumphost.yml with --connection local, no inventory."""
        playbook_path = f"{playbook_remote_dir}/{step.playbook}"
        cmd_parts = ["ansible-playbook", "--connection", "local", shlex.quote(playbook_path)]
        for key, val in step.extra_vars.items():
            cmd_parts.extend(["-e", shlex.quote(f"{key}={val}")])

        exit_code, tail, elapsed = self._run_command(" ".join(cmd_parts), timeout=600)
        result = StepResult(step=step, exit_code=exit_code, stdout_tail=tail, elapsed=elapsed)

        if exit_code != 0:
            logger.warning(f"  '{step.description}' exited {exit_code}")
        else:
            logger.info(f"  '{step.description}' completed in {elapsed:.1f}s")
        return result

    def run_plan(
        self,
        plan: List[PlaybookStep],
        inventory_path: Path,
        playbook_dir: Path,
        *,
        skip_missing: bool = True,
    ) -> List[StepResult]:
        """Bootstrap Ansible, upload, then execute every step in order.

        Stops at the first non-zero exit.

        Args:
            plan:            Ordered PlaybookStep list (from ``build_configure_plan``).
            inventory_path:  Local path to the generated inventory YAML.
            playbook_dir:    Local path to the ``ansible/`` directory.
            skip_missing:    If a playbook is missing after upload, warn and skip.

        Returns:
            One StepResult per attempted step.
        """
        # ── Bootstrap Ansible before anything else ─────────────────────
        self.bootstrap_ansible()

        # ── Upload ──────────────────────────────────────────────────────
        if self.key_path:
            self.upload_ssh_key(self.key_path)
        inv_remote = self.upload_inventory(inventory_path)
        pb_remote  = self.upload_playbooks(playbook_dir)

        # ── Execute ─────────────────────────────────────────────────────
        results: List[StepResult] = []
        for step in plan:
            # Verify the playbook made it to the linux utility server
            check_path = shlex.quote(f"{pb_remote}/{step.playbook}")
            _, check_out, _ = self._client.exec_command(
                f"test -f {check_path} && echo EXISTS"
            )
            if "EXISTS" not in check_out.read().decode():
                if skip_missing:
                    logger.warning(f"  Skipping '{step.description}' — {step.playbook} missing")
                    results.append(StepResult(
                        step=step, exit_code=0,
                        stdout_tail="(skipped — playbook not found)", elapsed=0.0,
                    ))
                    continue
                else:
                    raise FileNotFoundError(f"Playbook not found on linux utility server: {step.playbook}")

            if step.playbook == "setup_jumphost.yml":
                result = self._run_setup_jumphost(step, pb_remote)
            else:
                result = self.run_step(step, inv_remote, pb_remote)

            results.append(result)
            if result.exit_code != 0:
                logger.error(f"Plan halted at '{step.description}'")
                break

        return results
