"""Cooperative cancellation for content generation.

A generation is cancelled by the API endpoint (``POST /api/v1/runs/{id}/cancel``)
which flips a flag here *and* persists ``runs.status='cancelled'``. Long-running
pipeline steps poll ``is_cancelled(run_id)`` between units of work so the rest of
the job stops instead of burning more provider tokens.

Already-billed provider tokens are not refundable; the contract is only
"stop doing further work and never persist a cancelled generation as a success".
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_cancelled: set[str] = set()


class GenerationCancelled(RuntimeError):
    """Raised inside a pipeline when the user cancelled the run."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Generasi konten untuk run {run_id} dibatalkan oleh pengguna.")
        self.run_id = run_id


def request_cancel(run_id: str) -> bool:
    """Mark ``run_id`` as cancelled. Returns False when it was already marked."""
    if not run_id:
        return False
    with _lock:
        if run_id in _cancelled:
            return False
        _cancelled.add(run_id)
        return True


def is_cancelled(run_id: str | None) -> bool:
    if not run_id:
        return False
    with _lock:
        return run_id in _cancelled


def clear(run_id: str) -> None:
    """Forget a run's flag (called when the run is finished/reused)."""
    with _lock:
        _cancelled.discard(run_id)


def raise_if_cancelled(run_id: str | None) -> None:
    """Abort the current work unit if the run was cancelled."""
    if is_cancelled(run_id):
        raise GenerationCancelled(run_id or "")


def active_count() -> int:
    """Number of runs currently flagged as cancelled (diagnostics/tests)."""
    with _lock:
        return len(_cancelled)
