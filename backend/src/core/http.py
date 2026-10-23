"""HTTP requests with timeouts, retries, secret redaction, and event reporting."""
from email.utils import parsedate_to_datetime
import re
import time
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import requests
from requests import Response

from src.core.events import EventEmitter


_SECRET_KEYS = {"access_token", "api_key", "apikey", "token", "authorization", "x-api-key"}
_SECRET_PATTERN = re.compile(r"(?i)(access_token|api_key|authorization)(\s*[=:]\s*)([^\s&,;]+)")
_SECRET_QUERY_PATTERN = re.compile(r"(?i)(access_token|api_key|apikey|token)(=|%3D)([^\s&,;]+)")


def redact_url(url: str) -> str:
    """Remove secret query parameters from a URL while retaining non-secret context."""
    parts = urlsplit(url)
    query = [(key, "[REDACTED]" if key.lower() in _SECRET_KEYS else value)
             for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    safe_query = "&".join(f"{key}={value}" for key, value in query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, safe_query, ""))


def redact_text(text: str) -> str:
    """Redact common credential assignments from arbitrary response/error text."""
    sanitized = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", text)
    sanitized = _SECRET_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    sanitized = _SECRET_QUERY_PATTERN.sub(r"\1\2[REDACTED]", sanitized)
    return sanitized


class HttpClient:
    """Requests-compatible HTTP helper with a bounded retry policy."""

    def __init__(self, emitter: EventEmitter | None = None, *, timeout: float = 30.0,
                 max_attempts: int = 4, session: requests.Session | None = None) -> None:
        if timeout <= 0 or max_attempts < 1:
            raise ValueError("timeout and max_attempts must be positive")
        self.emitter = emitter
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.session = session or requests.Session()

    def request(self, method: str, url: str, *, step: str, provider: str,
                timeout: float | None = None, units: float | None = None,
                **kwargs: Any) -> Response:
        """Perform a request, retrying transient failures and emitting sanitized telemetry."""
        effective_timeout = timeout if timeout is not None else self.timeout
        if effective_timeout <= 0:
            raise ValueError("HTTP timeout must be positive")
        safe_url = redact_url(url)
        started = time.monotonic()
        response: Response | None = None
        try:
            for attempt in range(1, self.max_attempts + 1):
                try:
                    response = self.session.request(method, url, timeout=effective_timeout, **kwargs)
                except (requests.Timeout, requests.ConnectionError) as exc:
                    if attempt >= self.max_attempts:
                        raise RuntimeError(f"{provider} request timed out after {attempt} attempts") from exc
                    self._retry(step, provider, attempt, "timeout", 2 ** (attempt - 1))
                    time.sleep(2 ** (attempt - 1))
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.max_attempts:
                        delay = self._retry_delay(response, attempt)
                        self._retry(step, provider, attempt, f"HTTP {response.status_code}", delay)
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                self._emit(step, provider, safe_url, response.status_code, started, "ok", units=units)
                return response
            raise RuntimeError(f"{provider} request failed after {self.max_attempts} attempts")
        except Exception as exc:
            status_code = response.status_code if response is not None else None
            self._emit(step, provider, safe_url, status_code, started, "error",
                       {"error": redact_text(str(exc))[:500]}, units=units)
            raise RuntimeError(f"{provider} HTTP request failed ({type(exc).__name__})") from None

    def _retry_delay(self, response: Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), 60.0))
            except ValueError:
                try:
                    return max(0.0, min((parsedate_to_datetime(retry_after).timestamp() - time.time()), 60.0))
                except (TypeError, ValueError, OverflowError):
                    pass
        return float(min(2 ** (attempt - 1), 30))

    def _retry(self, step: str, provider: str, attempt: int, reason: str, delay: float) -> None:
        if self.emitter:
            self.emitter.emit("retry", provider, step=step, status="retry",
                              detail={"attempt": attempt, "reason": reason, "delay_seconds": delay})

    def _emit(self, step: str, provider: str, target: str, status_code: int | None,
              started: float, status: str, detail: dict[str, Any] | None = None,
              *, units: float | None = None) -> None:
        if self.emitter:
            event_detail = {"status_code": status_code, **(detail or {})}
            self.emitter.emit("http", provider, step=step, target=target, status=status, units=units,
                              duration_ms=(time.monotonic() - started) * 1000, detail=event_detail)
