"""Groq chat wrapper with transient retries, key rotation, usage reporting, and run budgets."""
import time
from typing import Any

from groq import Groq
from groq import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_random_exponential
import requests

from src import config
from src.core.events import EventEmitter
from src.core.keys import KeyPool, ProviderExhausted
from src.core.pricing import calculate_llm_cost


class BudgetExceeded(RuntimeError):
    """Raised when a configured run token/cost limit would be exceeded."""


def _is_network_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (APITimeoutError, APIConnectionError, TimeoutError, ConnectionError, requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        # Retry server error (500, 502, 503) maupun 429 atau 408
        return exc.status_code >= 500 or exc.status_code in (408, 429, 520, 524)
    return False


class LLMClient:
    """Expose a concise chat API while preserving provider response objects and key pool rotation."""

    def __init__(self, client: Any | None = None, *, emitter: EventEmitter | None = None,
                 budget: dict[str, float] | None = None, key_pool: KeyPool | None = None,
                 fallback_model: str | None = None) -> None:
        self.client = client
        self.emitter = emitter
        self.budget = budget or {}
        if key_pool is not None:
            self.key_pool = key_pool
            if emitter is not None and self.key_pool.emitter is None:
                self.key_pool.emitter = emitter
        else:
            self.key_pool = KeyPool("groq", emitter=emitter)
        self.fallback_model = fallback_model or config.opt("FALLBACK_MODEL", "")
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost_usd = 0.0
        self._clients: dict[str, Groq] = {}

    def _get_groq_client(self, api_key: str) -> Any:
        if self.client is not None:
            return self.client
        if api_key not in self._clients:
            self._clients[api_key] = Groq(api_key=api_key)
        return self._clients[api_key]

    def chat(self, messages: list[dict[str, Any]], *, step: str,
             model: str | None = None, tools: list[dict[str, Any]] | None = None,
             response_format: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Call chat completions with retries, key pool rotation on 429, and usage accounting."""
        primary_model = model or config.opt("GROQ_MODEL", "openai/gpt-oss-120b")
        models_to_try = [primary_model]
        if self.fallback_model and self.fallback_model != primary_model:
            models_to_try.append(self.fallback_model)

        last_exc: Exception | None = None
        for current_model in models_to_try:
            try:
                return self._chat_with_model(messages, step=step, model=current_model,
                                             tools=tools, response_format=response_format, **kwargs)
            except ProviderExhausted as exc:
                last_exc = exc
                if self.emitter:
                    self.emitter.emit("info", "groq", step=step, status="fallback_triggered",
                                      detail={"exhausted_model": current_model,
                                              "fallback_model": self.fallback_model or None})
                continue
            except Exception:
                raise

        if last_exc:
            raise last_exc
        raise ProviderExhausted("No LLM provider or keys available")

    def _chat_with_model(self, messages: list[dict[str, Any]], *, step: str,
                          model: str, tools: list[dict[str, Any]] | None = None,
                          response_format: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        arguments: dict[str, Any] = {"model": model, "messages": messages, **kwargs}
        if tools is not None:
            arguments["tools"] = tools
        if response_format is not None:
            arguments["response_format"] = response_format

        max_key_attempts = max(1, len(self.key_pool.keys))
        key_attempts = 0

        while key_attempts < max_key_attempts:
            try:
                api_key = self.key_pool.get_key()
            except ProviderExhausted:
                raise

            started = time.monotonic()
            client = self._get_groq_client(api_key)

            retryer = Retrying(
                retry=retry_if_exception(_is_network_retryable), stop=stop_after_attempt(4),
                wait=wait_random_exponential(multiplier=1, max=12), reraise=True,
                before_sleep=self._record_retry,
            )

            try:
                response = retryer(client.chat.completions.create, **arguments)
                usage = getattr(response, "usage", None)
                input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                cost = calculate_llm_cost(model, input_tokens, output_tokens)
                self._check_budget(input_tokens, output_tokens, cost)
                self.tokens_in += input_tokens
                self.tokens_out += output_tokens
                self.cost_usd += cost
                if self.emitter:
                    self.emitter.emit("llm", model, step=step, tokens_in=input_tokens,
                                      tokens_out=output_tokens, cost_usd=cost,
                                      duration_ms=(time.monotonic() - started) * 1000,
                                      detail={"usage_present": usage is not None,
                                              "key_id": KeyPool.mask_key(api_key)})
                return response
            except RateLimitError as exc:
                # If only 1 key is available, don't sleep in unit tests with cooldown duration 0
                cooldown_dur = self.key_pool.cooldown_seconds
                if len(self.key_pool.keys) <= 1 and cooldown_dur > 0:
                    time.sleep(min(3, cooldown_dur))
                self.key_pool.cooldown(api_key, duration=cooldown_dur if cooldown_dur == 0 else (5.0 if len(self.key_pool.keys) <= 1 else None))
                key_attempts += 1
                if self.emitter:
                    self.emitter.emit("retry", "groq", step=step, status="key_cooldown_429",
                                      detail={"key_id": KeyPool.mask_key(api_key),
                                              "attempt": key_attempts})
                continue
            except APIStatusError as exc:
                # APIStatusError yang tembus dari retryer (misalnya rate limit 429 atau upstream timeout dari Groq)
                status_code = getattr(exc, "status_code", 0)
                if status_code in (429, 500, 502, 503, 520, 524):
                    self.key_pool.cooldown(api_key, duration=self.key_pool.cooldown_seconds or 5.0)
                    key_attempts += 1
                    if self.emitter:
                        self.emitter.emit("retry", "groq", step=step, status=f"key_cooldown_{status_code}",
                                          detail={"key_id": KeyPool.mask_key(api_key),
                                                  "status_code": status_code,
                                                  "attempt": key_attempts})
                    continue
                if self.emitter:
                    self.emitter.emit("error", "llm_request", step=step, status="failed",
                                      detail={"model": model, "error_type": "APIStatusError",
                                              "status_code": status_code,
                                              "message": str(exc)[:300],
                                              "key_id": KeyPool.mask_key(api_key)})
                raise RuntimeError(f"LLM request failed (APIStatusError: {status_code} - {str(exc)[:150]})") from None
            except BudgetExceeded:
                raise
            except Exception as exc:
                if self.emitter:
                    self.emitter.emit("error", "llm_request", step=step, status="failed",
                                      detail={"model": model, "error_type": type(exc).__name__,
                                              "message": str(exc)[:300],
                                              "key_id": KeyPool.mask_key(api_key)})
                raise RuntimeError(f"LLM request failed ({type(exc).__name__}: {str(exc)[:150]})") from None

        raise ProviderExhausted(f"All keys exhausted after rate limits for model '{model}'")

    def _check_budget(self, tokens_in: int, tokens_out: int, cost: float) -> None:
        max_tokens = self.budget.get("max_tokens")
        max_cost = self.budget.get("max_cost_usd")
        if max_tokens is not None and self.tokens_in + self.tokens_out + tokens_in + tokens_out > max_tokens:
            raise BudgetExceeded("Run token budget exceeded")
        if max_cost is not None and self.cost_usd + cost > max_cost:
            raise BudgetExceeded("Run cost budget exceeded")

    def _record_retry(self, state: Any) -> None:
        if self.emitter:
            self.emitter.emit("retry", "groq", step="llm", status="retry",
                              detail={"attempt": state.attempt_number,
                                      "reason": type(state.outcome.exception()).__name__})
