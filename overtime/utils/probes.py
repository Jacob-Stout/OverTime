"""VM readiness probes — TCP port checks with retry.

No protocol-level handshake is performed.  A successful TCP connect to port 22
(Linux) or 5985 (Windows) is the signal that the OS is up and the listener is
bound.  Ansible will surface any further handshake issues on its own.
"""

import socket
import time
import logging
from typing import Dict
from dataclasses import dataclass

from .exceptions import OvertimeError

logger = logging.getLogger(__name__)

_PROBE_PORTS: Dict[str, int] = {
    "linux":      22,
    "cloud-init": 22,
    "windows":    5985,
}


class ProbeTimeout(OvertimeError):
    """Raised when a single-port probe exhausts its timeout."""


@dataclass
class ProbeResult:
    """Outcome of one VM probe."""
    vm_name:   str
    ip:        str
    port:      int
    reachable: bool
    elapsed:   float


def wait_for_port(
    host: str,
    port: int,
    *,
    timeout: int = 300,
    interval: int = 10,
) -> float:
    """Poll a TCP port until it accepts a connection.

    Returns:
        Elapsed seconds to first successful connect.

    Raises:
        ProbeTimeout: Port not reachable within *timeout*.
    """
    start    = time.monotonic()
    deadline = start + timeout

    while True:
        try:
            with socket.create_connection((host, port), timeout=5):
                return time.monotonic() - start
        except (socket.timeout, ConnectionRefusedError, OSError):
            if time.monotonic() >= deadline:
                raise ProbeTimeout(f"{host}:{port} not reachable after {timeout}s")
            time.sleep(min(interval, deadline - time.monotonic()))


def wait_for_vm(
    vm_name: str,
    ip: str,
    os_type: str,
    *,
    timeout: int = 300,
    interval: int = 10,
) -> ProbeResult:
    """Wait for a single VM to become reachable.  Does not raise on timeout."""
    bare_ip = ip.split("/")[0]
    port    = _PROBE_PORTS.get(os_type, 22)

    logger.info(f"Probing {vm_name} at {bare_ip}:{port} …")
    try:
        elapsed = wait_for_port(bare_ip, port, timeout=timeout, interval=interval)
        logger.info(f"  {vm_name}: reachable in {elapsed:.1f}s")
        return ProbeResult(vm_name=vm_name, ip=bare_ip, port=port, reachable=True, elapsed=elapsed)
    except ProbeTimeout:
        logger.warning(f"  {vm_name}: TIMEOUT after {timeout}s")
        return ProbeResult(vm_name=vm_name, ip=bare_ip, port=port, reachable=False, elapsed=float(timeout))
