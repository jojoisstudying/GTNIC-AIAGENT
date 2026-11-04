"""Tests for token budgeting: prompt compaction, TPM throttle, and 413 handling."""
import json
from types import SimpleNamespace

import httpx
import pytest
from groq import APIStatusError, RateLimitError

from src.core import tokens as token_budget
from src.core.llm import LLMClient, RequestTooLarge
from src.core.keys import KeyPool


def _too_large_error(status: int = 413, limit: int = 8000, requested: int = 10647) -> APIStatusError:
    body = {"error": {"message": (
        f"Request too large for model `openai/gpt-oss-120b` in organization `org_x` service tier "
        f"`on_demand` on tokens per minute (TPM): Limit {limit}, Requested {requested}, "
        "please reduce your message size. Try again in 7.13s."
    ), "type": "tokens", "code": "rate_limit_exceeded"}}
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status, request=request, json=body)
    cls = RateLimitError if status == 429 else APIStatusError
    return cls(body["error"]["message"], response=response, body=body)


class RecordingCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(outcomes, *, keys=("k1",), **kwargs):
    completions = RecordingCompletions(outcomes)
    provider = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    pool = KeyPool("groq", keys=list(keys), cooldown_seconds=0.0)
    events = []

    class Emitter:
        def emit(self, kind, name, **fields):
            events.append((kind, name, fields))

    client = LLMClient(provider, key_pool=pool, emitter=Emitter(), **kwargs)
    return client, completions, events


@pytest.fixture(autouse=True)
def _isolate_shared_limiters():
    """Limiter TPM kini proses-wide; tiap tes harus mulai dari kuota kosong."""
    token_budget.reset_shared_limiters()
    yield
    token_budget.reset_shared_limiters()


# ---------------------------------------------------------------- estimasi & kompaksi

def test_count_tokens_grows_with_content():
    small = token_budget.count_tokens([{"role": "user", "content": "halo"}])
    big = token_budget.count_tokens([{"role": "user", "content": "halo " * 500}])
    assert big > small * 10


def test_fit_messages_reduces_prompt_below_budget():
    messages = [
        {"role": "system", "content": "instruksi inti " * 20},
        {"role": "tool", "tool_call_id": "1", "content": json.dumps({"results": ["x" * 4000]})},
        {"role": "user", "content": "buat konten " * 400},
    ]
    fitted, estimated, compacted = token_budget.fit_messages(messages, 400)
    assert compacted is True
    assert estimated <= 400
    assert fitted[0]["content"].startswith("instruksi inti")     # system tidak dihapus
    assert fitted[-1]["content"].startswith("buat konten")       # instruksi tugas tetap terbaca


def test_fit_messages_keeps_small_prompt_untouched():
    messages = [{"role": "user", "content": "pendek"}]
    fitted, _estimated, compacted = token_budget.fit_messages(messages, 1000)
    assert compacted is False
    assert fitted == messages


def test_truncate_values_keeps_json_shape():
    node = {"sources": ["https://a.example/" + "x" * 300], "nested": {"a": ["y" * 200]}}
    small = token_budget.truncate_values(node, 40)
    assert list(small) == list(node)
    # URL tidak dipotong (lihat tests/test_research_sources.py), teks biasa dipotong.
    assert small["sources"][0] == node["sources"][0]
    assert all(len(s) <= 40 for s in small["nested"]["a"])
    assert json.dumps(small)


# ---------------------------------------------------------------- TPM throttle

def test_rate_limiter_waits_when_window_full(monkeypatch):
    limiter = token_budget.TokenRateLimiter(1000, window_seconds=60, max_wait_seconds=5)
    limiter.record(900)
    assert limiter.used() == 900
    # 900 + 500 melebihi 92% dari 1000 -> harus menunggu jendela bergeser
    assert limiter.delay_for(500) > 0


def test_rate_limiter_allows_when_small(monkeypatch):
    limiter = token_budget.TokenRateLimiter(10000)
    limiter.record(500)
    assert limiter.delay_for(500) == 0.0


def test_limiter_disabled_without_limit():
    limiter = token_budget.TokenRateLimiter(0)
    limiter.record(1_000_000)
    assert limiter.delay_for(1_000_000) == 0.0


def test_prompt_budget_reserves_output_tokens():
    assert token_budget.prompt_budget(8000, 2048) == int(8000 * 0.92) - 2048
    assert token_budget.prompt_budget(0, 2048) == 0
    assert token_budget.prompt_budget(100, 2048) == 0


def test_tpm_limit_from_env(monkeypatch):
    monkeypatch.setenv("LLM_TPM_LIMIT", "9000")
    monkeypatch.setenv("LLM_TPM_LIMITS", "openai/gpt-oss-20b=3000")
    assert token_budget.tpm_limit("openai/gpt-oss-20b") == 3000
    assert token_budget.tpm_limit("openai/gpt-oss-120b") == 9000
    monkeypatch.delenv("LLM_TPM_LIMIT")
    monkeypatch.delenv("LLM_TPM_LIMITS")
    assert token_budget.tpm_limit("openai/gpt-oss-120b") == 0


# ---------------------------------------------------------------- integrasi LLMClient

def test_default_max_completion_tokens_is_sent():
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5))
    client, completions, _ = _client([response])
    client.chat([{"role": "user", "content": "halo"}], step="test", model="m")
    assert completions.calls[0]["max_completion_tokens"] == token_budget.default_max_completion_tokens()


def test_prompt_compacted_before_request(monkeypatch):
    monkeypatch.setenv("LLM_TPM_LIMIT", "3000")
    monkeypatch.setenv("LLM_MAX_COMPLETION_TOKENS", "1000")
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5))
    client, completions, events = _client([response])
    giant = "x" * 60000
    client.chat([{"role": "system", "content": "aturan"}, {"role": "user", "content": giant}],
                step="test", model="m")
    sent = completions.calls[0]["messages"]
    assert sum(len(m["content"]) for m in sent) < len(giant)
    assert any(name == "token_budget" and fields.get("status") == "compacted"
               for _kind, name, fields in events)


def test_413_retries_once_with_smaller_output_then_raises(monkeypatch):
    monkeypatch.setenv("LLM_MAX_COMPLETION_TOKENS", "4096")
    client, completions, events = _client([_too_large_error(), _too_large_error()])
    with pytest.raises(RequestTooLarge) as excinfo:
        client.chat([{"role": "user", "content": "halo"}], step="planner", model="m")
    assert len(completions.calls) == 2                       # tidak ada retry tanpa akhir
    assert completions.calls[1]["max_completion_tokens"] < completions.calls[0]["max_completion_tokens"]
    message = str(excinfo.value)
    assert "8.000" in message and "10.647" in message         # angka dari body error dipakai
    assert "LLM_MAX_COMPLETION_TOKENS" in message
    assert any(fields.get("status") == "request_too_large" for _k, _n, fields in events)


def test_413_recovers_when_second_attempt_fits(monkeypatch):
    monkeypatch.setenv("LLM_MAX_COMPLETION_TOKENS", "4096")
    ok = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10))
    client, completions, _ = _client([_too_large_error(), ok])
    result = client.chat([{"role": "user", "content": "halo"}], step="planner", model="m")
    assert result is ok
    assert completions.calls[1]["max_completion_tokens"] <= 4096


def test_413_as_429_is_detected():
    client, completions, _ = _client([_too_large_error(status=429), _too_large_error(status=429)])
    with pytest.raises(RequestTooLarge):
        client.chat([{"role": "user", "content": "halo"}], step="planner", model="m")
    assert len(completions.calls) == 2


def test_daily_msg_does_not_trigger_413_path():
    """Error 400 biasa tetap jadi RuntimeError, bukan pesan TPM."""
    body = {"error": {"message": "invalid request: bad temperature", "type": "invalid_request_error"}}
    request = httpx.Request("POST", "https://api.groq.com")
    error = APIStatusError("invalid request", response=httpx.Response(400, request=request), body=body)
    client, _completions, _ = _client([error])
    with pytest.raises(RuntimeError) as excinfo:
        client.chat([{"role": "user", "content": "halo"}], step="planner", model="m")
    assert "too large" not in str(excinfo.value).lower()


def test_reasoning_effort_sent_when_configured(monkeypatch):
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))
    client, completions, _ = _client([response])
    client.chat([{"role": "user", "content": "halo"}], step="test", model="m")
    assert completions.calls[0]["reasoning_effort"] == "low"


def test_reasoning_effort_caller_wins(monkeypatch):
    monkeypatch.setenv("LLM_REASONING_EFFORT", "low")
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))
    client, completions, _ = _client([response])
    client.chat([{"role": "user", "content": "halo"}], step="test", model="m", reasoning_effort="high")
    assert completions.calls[0]["reasoning_effort"] == "high"


# ---------------------------------------------------------------- limiter bersama

def test_shared_limiter_counts_usage_across_clients(monkeypatch):
    """Dua LLMClient (dua run paralel) harus berbagi kuota TPM yang sama."""
    monkeypatch.setenv("LLM_TPM_LIMIT", "1000")
    ok = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=400, completion_tokens=100))
    first, _c1, _ = _client([ok, ok])
    second, _c2, _ = _client([ok])
    first.chat([{"role": "user", "content": "a"}], step="s", model="m")
    assert token_budget.shared_limiter("m", 1000).used() == 500
    # 500 + 1000 melewati 92% dari 1000 -> klien kedua harus menunggu, bukan kirim langsung
    assert second._limiter("m").delay_for(1000) > 0
    monkeypatch.delenv("LLM_TPM_LIMIT")


def test_override_disables_shared_limiter(monkeypatch):
    """tpm_limit_override (test/kalibrasi) tetap memakai limiter lokal."""
    client, _c, _ = _client([SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))])
    client.tpm_limit_override = 5
    limiter = client._limiter("m")
    assert limiter.limit_tpm == 5
    assert limiter is not token_budget.shared_limiter("m", 5)


def test_shared_limiter_can_be_disabled(monkeypatch):
    monkeypatch.setenv("LLM_TPM_LIMIT", "1000")
    monkeypatch.setenv("LLM_TPM_SHARE_LIMITER", "0")
    a, _ca, _ = _client([SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))])
    a.chat([{"role": "user", "content": "a"}], step="s", model="m")
    assert a._limiter("m").used() == 2
    assert token_budget.shared_limiter("m", 1000).used() == 0
    monkeypatch.delenv("LLM_TPM_LIMIT")
    monkeypatch.delenv("LLM_TPM_SHARE_LIMITER")


# ---------------------------------------------------------------- planner budget (413 nyata)

def _planner_static(research: dict, brand: dict, topic: str = "tren kue kering") -> dict:
    from src.carousel.agents import planner as P
    from src.carousel.sources import SourceCatalog
    cfg = P._prompt_budget_cfg(P._layout_catalog_prompt())
    return dict(
        brand=json.dumps(token_budget.truncate_values(brand, cfg["brand_value_chars"]),
                         ensure_ascii=False, separators=(",", ":")),
        topic=topic,
        research=json.dumps(token_budget.truncate_values(research, cfg["research_value_chars"]),
                            ensure_ascii=False, separators=(",", ":")),
        source_catalog=SourceCatalog.from_research(research).prompt_block(),
        layout_catalog=P._layout_catalog_prompt(), variety="")


def _big_research() -> dict:
    return {
        "facts": {"stats": [{"value": f"{i}%", "label": "x" * 150, "source_url": f"https://e.com/{i}"}
                            for i in range(10)],
                  "quotes": [{"text": "q" * 200, "source": "s" * 60} for _ in range(6)]},
        "trending_formats": [{"name": "n" * 40, "source_url": f"https://e.com/f{i}", "why": "w" * 250}
                             for i in range(8)],
        "content_angles": ["a" * 200 for _ in range(8)],
        "topic_candidates": [{"topic": "t" * 120, "suggested_angle": "s" * 200, "risk_notes": "r" * 200,
                              "source_urls": ["https://e.com/cand"]} for _ in range(6)],
        "posting_time": {"best_days": ["Senin"], "notes": "n" * 300},
        "sources": [f"https://e.com/src{i}" for i in range(12)],
    }


def test_planner_fit_meets_budget_and_keeps_layout_catalog(monkeypatch):
    """Prompt yang sudah dirapikan MUST fit: total request (prompt+output) <= TPM."""
    # Hermetik: .env lokal dengan LLM_TPM_LIMIT=0 (tanpa batas) tidak boleh mengubah hasil test.
    monkeypatch.setenv("LLM_TPM_LIMIT", "8000")
    monkeypatch.delenv("LLM_TPM_LIMITS", raising=False)
    from src.carousel.agents import planner as P
    cfg = P._prompt_budget_cfg(P._layout_catalog_prompt())
    budget = max(512, cfg["max_prompt_tokens"] - 400)
    static = _planner_static(_big_research(), {"company": "BakeNorder", "tone": "hangat"})
    fitted = P._fit_planner_static(static, budget)
    used = token_budget.count_tokens([{"role": "system", "content": P.SYSTEM},
                                      {"role": "user", "content": P.PROMPT.format(issues="", **fitted)}])
    assert used <= budget
    assert fitted["layout_catalog"] == static["layout_catalog"]   # katalog tidak pernah dipotong
    assert used + cfg["max_completion_tokens"] <= cfg["tpm_limit"]


def test_planner_output_adapts_to_small_tpm(monkeypatch):
    """TPM kecil: batas output planner turun otomatis, tidak perlu edit env manual."""
    from src.carousel.agents import planner as P
    big = P._prompt_budget_cfg("")
    monkeypatch.setenv("LLM_TPM_LIMIT", "4000")
    small = P._prompt_budget_cfg("")
    assert small["max_completion_tokens"] < big["max_completion_tokens"]
    assert small["max_completion_tokens"] >= 512          # JSON rencana tetap butuh ruang
    assert small["max_prompt_tokens"] > 0
    # prompt + output masih di bawah batas TPM
    assert small["max_prompt_tokens"] + small["max_completion_tokens"] <= 4000

