"""VideoPipeline stage riset: researcher diinjeksi, kegagalan riset tidak menghentikan run."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.video.pipeline import VideoPipeline


class Stop(Exception):
    pass


def _pipeline(researcher, events):
    sw = MagicMock()
    sw.generate_script.side_effect = Stop()  # hentikan setelah stage riset+script dipanggil
    ctx = SimpleNamespace(emit=lambda kind, name, **f: events.append((kind, name, f)))
    return VideoPipeline(scriptwriter=sw, broll_fetcher=MagicMock(), context=ctx, researcher=researcher), sw


def _run(vp, **kw):
    with pytest.raises(Stop):
        asyncio.run(vp.run_pipeline(topic="Apa itu HTTPS", target_duration_sec=15, **kw))


def test_research_context_is_passed_to_scriptwriter():
    events = []
    vp, sw = _pipeline(lambda t: {"ok": True, "context": f"fakta tentang {t}",
                                  "sources": [{"url": "https://a.test"}]}, events)
    _run(vp)
    assert sw.generate_script.call_args.kwargs["research_context"] == "fakta tentang Apa itu HTTPS"
    done = [e for e in events if e[1] == "video_research_done"]
    assert done and done[0][2]["detail"]["urls"] == ["https://a.test"]


def test_research_failure_is_warned_and_run_continues_without_context():
    events = []
    vp, sw = _pipeline(lambda t: {"ok": False, "error": "tidak ada kunci Tavily"}, events)
    _run(vp)
    assert sw.generate_script.call_args.kwargs["research_context"] is None
    skipped = [e for e in events if e[1] == "video_research_skipped"]
    assert skipped and skipped[0][2]["status"] == "failed"
    assert "tidak ada kunci Tavily" in skipped[0][2]["detail"]["reason"]


def test_researcher_exception_does_not_crash_pipeline():
    def boom(t):
        raise RuntimeError("jaringan putus")
    events = []
    vp, sw = _pipeline(boom, events)
    _run(vp)
    assert sw.generate_script.called
    assert any(e[1] == "video_research_skipped" for e in events)


def test_explicit_research_context_skips_researcher():
    called = []
    vp, sw = _pipeline(lambda t: called.append(t) or {"ok": True, "context": "x"}, [])
    _run(vp, research_context="sudah ada")
    assert called == [] and sw.generate_script.call_args.kwargs["research_context"] == "sudah ada"


def test_no_researcher_means_no_research():
    vp, sw = _pipeline(None, [])
    _run(vp)
    assert sw.generate_script.call_args.kwargs["research_context"] is None