"""CPU / memory via psutil, NVIDIA GPUs via ``nvidia-smi``."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time

from jarvis_core.domain.records import GpuStatus, SystemStatus

NVIDIA_SMI_QUERY = "name,utilization.gpu,memory.used,memory.total,temperature.gpu"


def _number(value: str) -> float | None:
    try:
        return float(value.strip())
    except ValueError:
        return None  # "[N/A]" on some boards


def parse_nvidia_smi(output: str) -> tuple[GpuStatus, ...]:
    """Parse ``nvidia-smi --query-gpu=… --format=csv,noheader,nounits`` output."""
    gpus: list[GpuStatus] = []
    for line in output.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        gpus.append(
            GpuStatus(
                name=parts[0],
                utilization_pct=_number(parts[1]) or 0.0,
                memory_used_mb=_number(parts[2]) or 0.0,
                memory_total_mb=_number(parts[3]) or 0.0,
                temperature_c=_number(parts[4]) if len(parts) > 4 else None,
            )
        )
    return tuple(gpus)


def query_nvidia_smi(timeout_s: float = 2.0) -> tuple[GpuStatus, ...]:
    """Ask ``nvidia-smi`` about every GPU; empty if there is none."""
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return ()
    try:
        result = subprocess.run(
            [executable, f"--query-gpu={NVIDIA_SMI_QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    return parse_nvidia_smi(result.stdout)


class PsutilSystemMonitor:
    """Implements :class:`~jarvis_core.domain.ports.SystemMonitor`."""

    def __init__(self) -> None:
        import psutil

        self._psutil = psutil
        psutil.cpu_percent(None)  # prime: the first non-blocking reading is meaningless

    async def status(self) -> SystemStatus:
        """Snapshot of CPU, RAM and GPUs (runs in a worker thread)."""
        return await asyncio.to_thread(self._snapshot)

    def _snapshot(self) -> SystemStatus:
        memory = self._psutil.virtual_memory()
        return SystemStatus(
            cpu_percent=float(self._psutil.cpu_percent(None)),
            memory_used_gb=round((memory.total - memory.available) / 1024**3, 2),
            memory_total_gb=round(memory.total / 1024**3, 2),
            gpus=query_nvidia_smi(),
            uptime_s=round(time.time() - self._psutil.boot_time()),
        )
