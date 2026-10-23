"""Run-scoped dependencies and lifecycle for a single content generation."""
from dataclasses import dataclass, field
import uuid
from typing import Any

from sqlalchemy.orm import Session

from src.core.db import Run, SessionLocal, sessionmaker
from src.core.events import EventEmitter
from src.core.http import HttpClient
from src.core.keys import KeyPool
from src.core.llm import LLMClient


@dataclass
class RunContext:
    """Shared state and clients passed from pipeline orchestration into agents/tools."""
    run_id: str
    brand: dict[str, Any]
    session: Session
    emitter: EventEmitter
    llm: LLMClient
    http: HttpClient
    budget: dict[str, float] = field(default_factory=dict)
    tavily_pool: KeyPool = field(default_factory=lambda: KeyPool("tavily"))

    def emit(self, kind: str, name: str, **fields: Any) -> None:
        """Emit a run-scoped event without allowing telemetry to interrupt a run."""
        self.emitter.emit(kind, name, **fields)

    def close(self) -> None:
        """Release the run's database session."""
        self.session.close()


def create_run_context(topic: str, brand: dict[str, Any], *,
                       budget: dict[str, float] | None = None,
                       run_id: str | None = None,
                       session_factory: sessionmaker[Session] = SessionLocal) -> RunContext:
    """Create a run context, optionally attaching it to an existing run."""
    session = session_factory()
    if run_id is None:
        run_id = uuid.uuid4().hex
        run = Run(id=run_id, topic=topic, brand_id=str(brand.get("company", "")), status="running")
        session.add(run)
        session.commit()
    elif session.get(Run, run_id) is None:
        session.close()
        raise ValueError(f"Run '{run_id}' tidak ditemukan; tidak bisa melanjutkan konteks")

    emitter = EventEmitter(run_id, session_factory)
    groq_pool = KeyPool("groq", emitter=emitter)
    tavily_pool = KeyPool("tavily", emitter=emitter)
    llm = LLMClient(emitter=emitter, budget=budget, key_pool=groq_pool)
    http = HttpClient(emitter)
    return RunContext(run_id, brand, session, emitter, llm, http, budget or {}, tavily_pool=tavily_pool)
