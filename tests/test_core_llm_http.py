"""Tests for resilient LLM calls and sanitized HTTP errors."""
from types import SimpleNamespace

import pytest
import requests

from src.core.http import HttpClient, redact_text, redact_url
from src.core.llm import LLMClient


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        result = next(self.outcomes)
        if isinstance(result, Exception):
            raise result
        return result


def test_llm_retries_and_records_usage() -> None:
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=7)
    response = SimpleNamespace(usage=usage)
    completions = FakeCompletions([requests.Timeout("temporary"), response])
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    events = []
    emitter = SimpleNamespace(emit=lambda *args, **kwargs: events.append((args, kwargs)))

    actual = LLMClient(client, emitter=emitter).chat(
        [{"role": "user", "content": "hello"}], step="research", model="demo"
    )

    assert actual is response
    assert completions.calls == 2
    assert any(args[0] == "retry" for args, _kwargs in events)
    llm_event = next(kwargs for args, kwargs in events if args[0] == "llm")
    assert llm_event["tokens_in"] == 12
    assert llm_event["tokens_out"] == 7


def test_http_error_redacts_token_from_message_and_event() -> None:
    secret = "sensitive-token-value"

    class FakeResponse:
        status_code = 400
        headers = {}
        text = f"request rejected?access_token={secret} Authorization: Bearer {secret}"

        def raise_for_status(self):
            raise requests.HTTPError(self.text)

    class FakeSession:
        def request(self, *_args, **_kwargs):
            return FakeResponse()

    events = []
    emitter = SimpleNamespace(emit=lambda *args, **kwargs: events.append((args, kwargs)))
    http = HttpClient(emitter, session=FakeSession(), max_attempts=1)

    with pytest.raises(RuntimeError) as error:
        http.request("GET", "https://example.test/path?access_token=" + secret,
                     step="test", provider="example")

    assert secret not in str(error.value)
    assert secret not in str(events)
    assert "[REDACTED]" in redact_url("https://example.test/?api_key=" + secret)
    assert secret not in redact_text("Authorization: Bearer " + secret)
