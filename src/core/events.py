"""Persist structured run events and emit concise terminal summaries."""
from datetime import datetime, timezone
import json
import sys
from typing import Any, Callable

from sqlalchemy.orm import Session, sessionmaker

from src.core.db import Event


class EventEmitter:
    """Best-effort event writer that never interrupts the pipeline caller."""

    def __init__(self, run_id: str | None, session_factory: sessionmaker[Session],
                 printer: Callable[[str], Any] = print) -> None:
        self.run_id = run_id
        self.session_factory = session_factory
        self.printer = printer

    def emit(self, kind: str, name: str, *, step: str = "", target: str | None = None,
             tokens_in: int | None = None, tokens_out: int | None = None,
             units: float | None = None, cost_usd: float | None = None,
             duration_ms: float | None = None, status: str = "ok",
             detail: dict[str, Any] | None = None) -> None:
        """Write the event and print it; database/console errors are swallowed by contract."""
        event = Event(
            run_id=self.run_id, ts=datetime.now(timezone.utc), step=step, kind=kind,
            name=name, target=target, tokens_in=tokens_in, tokens_out=tokens_out,
            units=units, cost_usd=cost_usd, duration_ms=duration_ms,
            status=status, detail_json=json.dumps(detail or {}, ensure_ascii=False, default=str),
        )
        try:
            with self.session_factory() as session:
                session.add(event)
                session.commit()
        except Exception as exc:
            print(f"[event persistence failed: {type(exc).__name__}]", file=sys.stderr)
        try:
            stamp = datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")
            fields = []
            if tokens_in is not None:
                fields.append(f"in={tokens_in}")
            if tokens_out is not None:
                fields.append(f"out={tokens_out}")
            if units is not None:
                fields.append(f"units={units:g}")
            if cost_usd is not None:
                fields.append(f"${cost_usd:.4f}")
            if duration_ms is not None:
                fields.append(f"{duration_ms / 1000:.1f}s")
            suffix = " | " + " ".join(fields) if fields else ""
            self.printer(f"[{stamp}] {step or '-'} | {kind} {name}{suffix} ({status})")
        except Exception as exc:
            print(f"[event output failed: {type(exc).__name__}]", file=sys.stderr)
