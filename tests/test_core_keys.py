"""Tests for core/keys.py KeyPool, rotation, cooldown, and LLM fallback."""
import pytest
from groq import RateLimitError
import httpx

from src.core.events import EventEmitter
from src.core.keys import KeyPool, ProviderExhausted
from src.core.llm import LLMClient


def test_key_pool_env_and_round_robin(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "key-1, key-2 , key-3")
    pool = KeyPool("groq")
    assert pool.keys == ["key-1", "key-2", "key-3"]

    k1 = pool.get_key()
    k2 = pool.get_key()
    k3 = pool.get_key()
    k4 = pool.get_key()

    assert k1 == "key-1"
    assert k2 == "key-2"
    assert k3 == "key-3"
    assert k4 == "key-1"


def test_key_pool_mask_key():
    masked = KeyPool.mask_key("super-secret-key-12345")
    assert len(masked) == 4
    assert "secret" not in masked
    assert KeyPool.mask_key("") == "none"


def test_key_pool_cooldown_and_exhaustion():
    pool = KeyPool("groq", keys=["k1", "k2"], cooldown_seconds=10)
    assert pool.get_key() == "k1"

    pool.cooldown("k1")
    assert pool.get_key() == "k2"

    pool.cooldown("k2")
    with pytest.raises(ProviderExhausted) as excinfo:
        pool.get_key()
    assert "cooling down" in str(excinfo.value)


class MockGroqChat:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    @property
    def completions(self):
        return self

    @property
    def chat(self):
        return self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.outcomes:
            raise RuntimeError("No more mocked outcomes")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class DummyUsage:
    prompt_tokens = 10
    completion_tokens = 20


class DummyResponse:
    usage = DummyUsage()


def test_llm_rotation_on_429():
    dummy_req = httpx.Request("POST", "https://api.groq.com")
    dummy_res = httpx.Response(429, request=dummy_req)
    rate_err = RateLimitError("Rate limit exceeded", response=dummy_res, body=None)

    # Provider will fail on key-1 with 429, succeed on key-2
    mock_provider = MockGroqChat([rate_err, DummyResponse()])

    events = []
    class DummyEmitter:
        def emit(self, kind, name, **fields):
            events.append((kind, name, fields))

    pool = KeyPool("groq", keys=["k1", "k2"])
    client = LLMClient(client=mock_provider, key_pool=pool, emitter=DummyEmitter())

    res = client.chat([{"role": "user", "content": "hi"}], step="test_step")
    assert res is not None
    assert len(mock_provider.calls) == 2

    # Check that events recorded cooldown
    cooldown_events = [e for e in events if e[0] == "key" and e[2].get("status") == "cooldown"]
    assert len(cooldown_events) == 1
    assert cooldown_events[0][2]["detail"]["key_id"] == KeyPool.mask_key("k1")


def test_llm_fallback_model_on_exhausted():
    dummy_req = httpx.Request("POST", "https://api.groq.com")
    dummy_res = httpx.Response(429, request=dummy_req)
    rate_err = RateLimitError("Rate limit exceeded", response=dummy_res, body=None)

    # Only 1 key: primary model will exhaust key, fallback will also be attempted
    mock_provider = MockGroqChat([rate_err, DummyResponse()])

    pool = KeyPool("groq", keys=["k1"], cooldown_seconds=0.001)

    # Cooldown k1 manually to trigger fallback directly
    pool.cooldown("k1", duration=10.0)

    # When fallback model is called, suppose we reset or provide key for fallback or test fallback attempt
    # Let's test that fallback model is tried when primary fails with ProviderExhausted:
    # If pool is reset for fallback or we test that fallback model is called
    pool2 = KeyPool("groq", keys=["k1"], cooldown_seconds=0.0)
    mock_client = MockGroqChat([rate_err, DummyResponse()])
    client = LLMClient(client=mock_client, key_pool=pool2, fallback_model="llama-3.1-8b-instant")
    res = client.chat([{"role": "user", "content": "hi"}], step="test_step", model="gpt-oss-120b")
    assert res is not None
    assert mock_client.calls[0]["model"] == "gpt-oss-120b"
    assert mock_client.calls[1]["model"] == "llama-3.1-8b-instant"
