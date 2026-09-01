"""research.post.sweeps — parameter sweep engines, controls and report builders.

Worker-count policy
-------------------
Sweeps parallelise with ``multiprocessing.Pool`` over grid units. Each worker
holds its own copy of the OHLCV frame plus scratch arrays for the indicators
it is evaluating, so both memory and CPU scale with the pool size.

Measured on XAUUSD_M5 (1,443,451 rows): the frame alone is ~58 MB resident per
worker, with a ~221 MB transient spike while loading. Add the interpreter and
per-config indicator arrays and a worker sits in the low hundreds of MB.

The historical defaults across these scripts were ``cpu_count() - 1`` (or a
hard-coded 7/8), which saturates an 8-core desktop and makes the machine
unusable for anything else while a sweep runs. :func:`default_workers` instead
leaves half the cores free and caps the pool against actual free memory, so a
sweep degrades to fewer workers on a small host rather than being OOM-killed.

Override explicitly when the machine is otherwise idle::

    SWEEP_WORKERS=8 python -m research.post.sweeps.run_cnk_sweep
"""
from __future__ import annotations

import os

# Low-hundreds-of-MB per worker; see module docstring for the measurement.
PER_WORKER_MB = 400
# Held back for the OS, desktop and anything else the user is running.
RESERVE_MB = 2048


def _mem_available_mb() -> int | None:
    """Free memory in MB per /proc/meminfo, or None where that is unreadable."""
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        return None
    return None


def default_workers(
    per_worker_mb: int = PER_WORKER_MB,
    reserve_mb: int = RESERVE_MB,
) -> int:
    """Pool size that leaves the host usable while a sweep runs.

    ``SWEEP_WORKERS`` overrides the calculation entirely. Otherwise the result
    is half the cores, capped by how many workers current free memory affords.
    """
    override = os.environ.get("SWEEP_WORKERS")
    if override:
        return max(1, int(override))

    cores = max(1, (os.cpu_count() or 2) // 2)

    available_mb = _mem_available_mb()
    if available_mb is None:
        return cores

    affordable = (available_mb - reserve_mb) // per_worker_mb
    return max(1, min(cores, affordable))
