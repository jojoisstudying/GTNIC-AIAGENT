"""Groq chat wrapper with transient retries, key rotation, usage reporting, and run budgets."""
import re
import time
from typing import Any

from groq import Groq
from groq import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_random_exponential
import requests

from src import config
from src.core import tokens as token_budget
from src.core.events import EventEmitter
from src.core.keys import KeyPool, ProviderExhausted
from src.core.pricing import calculate_llm_cost


class BudgetExceeded(RuntimeError):
    """Raised when a configured run token/cost limit would be exceeded."""


class RequestTooLarge(RuntimeError):
    """Permintaan melebihi batas token per menit (TPM) penyedia; tidak diulang otomatis."""


class ToolCallInvalid(RuntimeError):
    """Model menghasilkan tool call yang ditolak provider (mis. nama tool salah)."""


class ModelUnavailable(RuntimeError):
    """Model yang dikonfigurasi tidak ada lagi di penyedia (mis. sudah deprecated)."""


def _error_message(exc: BaseException) -> str:
    """Ambil pesan error asli dari body API agar tidak terpotong jadi JSON mentah."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str):
            return err
    return str(exc)


def _is_tool_call_error(exc: APIStatusError) -> bool:
    """Groq membalas 400 + code tool_use_failed saat model salah menyebut nama tool."""
    if getattr(exc, "status_code", 0) != 400:
        return False
    text = f"{_error_message(exc)} {exc}".lower()
    return any(marker in text for marker in
               ("tool_use_failed", "tool call validation failed", "not in request.tools"))


def _is_network_retryable(exc: BaseException) -> bool:
    if isinstance(exc, RateLimitError):
        return False
    if isinstance(exc, (APITimeoutError, APIConnectionError, TimeoutError, ConnectionError, requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        # Rate limit 429 should rotate keys immediately, not retry on the same exhausted key
        if exc.status_code == 429:
            return False
        return exc.status_code >= 500 or exc.status_code in (408, 520, 524)
    return False


_TPM_PATTERN = re.compile(r"limit\s*(\d[\d,]*)\D{0,80}?requested\s*(\d[\d,]*)", re.IGNORECASE | re.DOTALL)


_TPD_UNTIL: dict[str, float] = {}   # model -> waktu (epoch) kuota harian (TPD) diperkirakan pulih


def _note_tpd(model: str, exc: BaseException) -> None:
    """Catat 429 'tokens per day' beserta estimasi pulihnya, supaya sistem tidak membakar sisa token."""
    text = _error_message(exc)
    if "tokens per day" not in text.lower():
        return
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", text)
    secs = 3600.0
    if m and any(m.groups()):
        secs = int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3) or 0)
    _TPD_UNTIL[model] = time.time() + secs + 30


def tpd_all_blocked() -> bool:
    """True bila model utama dan model cadangan Groq sama-sama kehabisan kuota harian."""
    now = time.time()
    models = {config.opt("GROQ_MODEL", "openai/gpt-oss-120b"), config.opt("FALLBACK_MODEL", "") or ""}
    models.discard("")
    return bool(models) and all(_TPD_UNTIL.get(m, 0) > now for m in models)


def _is_request_too_large(exc: BaseException) -> bool:
    """True untuk 413 / error TPM Groq ("Request too large ... Limit 8000, Requested 10496").

    Groq kadang membalasnya sebagai 413, kadang sebagai RateLimitError (429) dengan
    teks yang sama. Keduanya bukan error sementara: mengulang request yang sama
    hanya membakar kuota, jadi harus ditangani sekali dan dilaporkan jelas.
    """
    status = getattr(exc, "status_code", 0) or 0
    text = f"{_error_message(exc)} {exc}".lower()
    markers = ("request too large", "tokens per minute", " tpm", "reduce your message size",
               "reduce the length of the messages")
    if status == 413 and any(m in text for m in markers):
        return True
    return status in (413, 429) and any(m in text for m in ("request too large", "tokens per minute"))


def _tpm_numbers(exc: BaseException) -> tuple[int | None, int | None]:
    """Ambil (limit, requested) dari body error TPM bila penyedia menyebutkannya."""
    match = _TPM_PATTERN.search(_error_message(exc))
    if not match:
        return None, None
    try:
        return int(match.group(1).replace(",", "")), int(match.group(2).replace(",", ""))
    except ValueError:
        return None, None


def too_large_message(model: str, *, limit: int | None, requested: int | None) -> str:
    """Pesan 413 yang bisa ditindaklanjuti operator (bahasa Indonesia)."""
    detail = ""
    if limit and requested:
        detail = (f"Batas {limit:,} token/menit (TPM), permintaan {requested:,} token "
                  f"(kelebihan {requested - limit:,}).").replace(",", ".")
    elif limit:
        detail = (f"Batas {limit:,} token/menit (TPM).").replace(",", ".")
    elif requested:
        detail = (f"Permintaan {requested:,} token melebihi batas TPM akun.").replace(",", ".")
    hint = (
        "Prompt sudah diringkas otomatis, tetapi masih melebihi kuota menit. "
        "Langkah yang bisa dilakukan: (1) tunggu ±1 menit lalu jalankan ulang — kuota TPM "
        "dihitung per menit; (2) turunkan LLM_MAX_COMPLETION_TOKENS di backend/.env; "
        "(3) isi LLM_TPM_LIMIT sesuai batas akun Groq supaya prompt dipangkas lebih agresif; "
        "(4) pakai GROQ_API_KEYS dengan beberapa kunci untuk menyebar beban."
    )
    return f"Permintaan ke model '{model}' terlalu besar untuk batas token penyedia. {detail} {hint}".strip()


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
        self._limiters: dict[str, token_budget.TokenRateLimiter] = {}
        self.tpm_limit_override: int | None = None     # dipakai test / kalibrasi manual
        # Limiter dibagi antar-LLMClient dalam satu proses: TPM dihitung per akun,
        # bukan per run, jadi run paralel tidak boleh mengira punya kuota penuh semua.
        self.share_tpm_limiter = (config.opt("LLM_TPM_SHARE_LIMITER", "1") or "1").strip().lower() \
            not in {"0", "false", "no", "off"}

    def _limiter(self, model: str) -> token_budget.TokenRateLimiter:
        limit = self.tpm_limit_override if self.tpm_limit_override is not None else token_budget.tpm_limit(model)
        limit = max(0, int(limit or 0))
        limiter = self._limiters.get(model)
        if limiter is None or limiter.limit_tpm != limit:
            if self.share_tpm_limiter and self.tpm_limit_override is None:
                limiter = token_budget.shared_limiter(model, limit)
            else:
                limiter = token_budget.TokenRateLimiter(limit)
            self._limiters[model] = limiter
        return limiter

    def _get_groq_client(self, api_key: str) -> Any:
        if self.client is not None:
            return self.client
        if api_key not in self._clients:
            self._clients[api_key] = Groq(api_key=api_key, timeout=float(config.opt("LLM_TIMEOUT_SECONDS", "90") or 90), max_retries=1)
        return self._clients[api_key]

    def chat(self, messages: list[dict[str, Any]], *, step: str,
             model: str | None = None, tools: list[dict[str, Any]] | None = None,
             response_format: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Groq dulu; bila semua key habis/cooldown: penyedia cadangan (jika diisi), lalu tunggu & coba lagi."""
        def _strip_extra(msgs):
            """Groq menolak field asing: buang extra_content (milik Gemini) sebelum dikirim ke Groq."""
            out = []
            for m in msgs:
                if isinstance(m, dict) and m.get("tool_calls"):
                    m = {**m, "tool_calls": [{k: v for k, v in tc.items() if k != "extra_content"}
                                             if isinstance(tc, dict) else tc for tc in m["tool_calls"]]}
                out.append(m)
            return out

        groq_messages = _strip_extra(messages)
        if tpd_all_blocked():
            alt = self._fallback_chat(messages, step=step, tools=tools, response_format=response_format, **kwargs)
            if alt is not None:
                return alt
        for attempt in range(4):
            try:
                return self._chat_once(groq_messages, step=step, model=model, tools=tools,
                                       response_format=response_format, **kwargs)
            except Exception as exc:  # noqa: BLE001
                alt = self._fallback_chat(messages, step=step, tools=tools,
                                          response_format=response_format, **kwargs)
                if alt is not None:
                    return alt
                if not isinstance(exc, ProviderExhausted):
                    raise
                if attempt == 3:
                    raise
                wait = min(65.0, max(10.0, float(getattr(self.key_pool, "cooldown_seconds", 60.0) or 60.0)))
                if self.emitter:
                    self.emitter.emit("retry", "groq", step=step, status="waiting_key_cooldown",
                                      detail={"wait_seconds": wait, "attempt": attempt + 1})
                time.sleep(wait)

    def _fallback_chat(self, messages: list[dict[str, Any]], *, step: str, **kwargs: Any) -> Any:
        """Penyedia cadangan kompatibel OpenAI (Gemini, Cerebras, Mistral, dll).

        Aktif hanya bila FALLBACK_LLM_API_KEY, FALLBACK_LLM_BASE_URL, FALLBACK_LLM_MODEL terisi di .env.
        Mengembalikan None bila tidak dikonfigurasi atau cadangan juga gagal.
        """
        import json as _json
        from types import SimpleNamespace
        key = (config.opt("FALLBACK_LLM_API_KEY", "") or "").strip()
        base = (config.opt("FALLBACK_LLM_BASE_URL", "") or "").strip().rstrip("/")
        fb_models = [m.strip() for m in (config.opt("FALLBACK_LLM_MODEL", "") or "").split(",") if m.strip()]
        if not (key and base and fb_models):
            return None
        for fb_model in fb_models:          # coba berurutan; model yang sedang ramai (503) dilewati
            body: dict[str, Any] = {"model": fb_model, "messages": messages}
            for k_src, k_dst in (("temperature", "temperature"), ("max_completion_tokens", "max_tokens"),
                                 ("tools", "tools"), ("tool_choice", "tool_choice"),
                                 ("response_format", "response_format")):
                if kwargs.get(k_src) is not None:
                    body[k_dst] = kwargs[k_src]
            try:
                r = requests.post(f"{base}/chat/completions", json=body, timeout=120,
                                  headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                data = _json.loads(r.text, object_hook=lambda d: SimpleNamespace(**d))
                if self.emitter:
                    self.emitter.emit("retry", "fallback_llm", step=step, status="fallback_provider_used",
                                      detail={"model": fb_model})
                return data
            except Exception as exc:  # noqa: BLE001
                if self.emitter:
                    self.emitter.emit("warn", "fallback_llm", step=step, status="fallback_provider_failed",
                                      detail={"model": fb_model, "error": str(exc)[:200]})
        return None

    def _chat_once(self, messages: list[dict[str, Any]], *, step: str,
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
            except ToolCallInvalid as exc:
                last_exc = exc
                if current_model == models_to_try[-1]:
                    raise RuntimeError(
                        f"{exc}. Ganti GROQ_MODEL ke model yang lebih patuh tool calling "
                        f"(mis. openai/gpt-oss-120b) di backend/.env, lalu restart backend."
                    ) from None
                if self.emitter:
                    self.emitter.emit("retry", "groq", step=step, status="fallback_model_tool_call",
                                      detail={"failed_model": current_model,
                                              "fallback_model": self.fallback_model or None,
                                              "message": str(exc)[:250]})
                continue
            except ModelUnavailable as exc:
                last_exc = exc
                if current_model == models_to_try[-1]:
                    raise RuntimeError(
                        f"{exc} Periksa GROQ_MODEL dan FALLBACK_MODEL di backend/.env "
                        f"(daftar model: https://console.groq.com/docs/models)."
                    ) from None
                if self.emitter:
                    self.emitter.emit("retry", "groq", step=step, status="model_unavailable",
                                      detail={"failed_model": current_model,
                                              "fallback_model": self.fallback_model or None})
                continue
            except Exception:
                raise

        if last_exc:
            raise last_exc
        raise ProviderExhausted("No LLM provider or keys available")

    def _prepare_request(self, messages: list[dict[str, Any]], *, model: str, step: str,
                         tools: list[dict[str, Any]] | None,
                         kwargs: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Terapkan anggaran token SEBELUM request dikirim.

        - Token output dibatasi (``max_completion_tokens``) bila caller tidak menentukan.
        - Prompt dipangkas agar prompt + output muat di kuota TPM model.
        - Request ditahan sebentar kalau kuota menit berjalan sudah hampir habis.
        """
        arguments = dict(kwargs)
        # gpt-oss memakai token "reasoning" yang ikut dihitung sebagai output. Untuk step
        # yang hanya perlu JSON terstruktur, effort rendah menghemat ratusan token dan
        # menyisakan ruang lebih besar untuk prompt. Diatur lewat env, bukan di-hardcode.
        if "reasoning_effort" not in arguments:
            default_effort = (config.opt("LLM_REASONING_EFFORT", "") or "").strip().lower()
            if default_effort in {"low", "medium", "high"}:
                arguments["reasoning_effort"] = default_effort
        requested_output = arguments.get("max_completion_tokens") or arguments.get("max_tokens")
        if not requested_output:
            requested_output = token_budget.default_max_completion_tokens()
            arguments["max_completion_tokens"] = requested_output
        try:
            requested_output = int(requested_output)
        except (TypeError, ValueError):
            requested_output = token_budget.default_max_completion_tokens()
            arguments["max_completion_tokens"] = requested_output

        limiter = self._limiter(model)
        budget_tokens = token_budget.prompt_budget(limiter.limit_tpm, requested_output)
        fitted, estimated, compacted = token_budget.fit_messages(messages, budget_tokens, tools=tools)
        if compacted and self.emitter:
            self.emitter.emit("info", "token_budget", step=step, status="compacted",
                              tokens_in=estimated,
                              detail={"model": model, "estimated_prompt_tokens": estimated,
                                      "prompt_budget": budget_tokens,
                                      "max_completion_tokens": requested_output})

        waited = limiter.wait(estimated + requested_output)
        if waited and self.emitter:
            self.emitter.emit("info", "token_budget", step=step, status="tpm_throttled",
                              tokens_in=estimated,
                              detail={"model": model, "waited_seconds": round(waited, 1),
                                      "tpm_limit": limiter.limit_tpm})
        return fitted, arguments

    def _chat_with_model(self, messages: list[dict[str, Any]], *, step: str,
                          model: str, tools: list[dict[str, Any]] | None = None,
                          response_format: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        messages, kwargs = self._prepare_request(messages, model=model, step=step, tools=tools, kwargs=kwargs)
        arguments: dict[str, Any] = {"model": model, "messages": messages, **kwargs}
        if tools is not None:
            arguments["tools"] = tools
        if response_format is not None:
            arguments["response_format"] = response_format

        max_key_attempts = max(1, len(self.key_pool.keys))
        key_attempts = 0
        tool_retries = 0
        too_large_retry = False      # paling banyak satu kali: coba lagi dengan output lebih kecil

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
                self._limiter(model).record(input_tokens + output_tokens)
                if self.emitter:
                    self.emitter.emit("llm", model, step=step, tokens_in=input_tokens,
                                      tokens_out=output_tokens, cost_usd=cost,
                                      duration_ms=(time.monotonic() - started) * 1000,
                                      detail={"usage_present": usage is not None,
                                              "key_id": KeyPool.mask_key(api_key)})
                return response
            except RateLimitError as exc:
                if _is_request_too_large(exc):
                    if too_large_retry:
                        raise self._too_large_error(model, exc) from None
                    too_large_retry = True
                    messages, arguments = self._shrink_after_413(
                        messages, arguments, model=model, step=step, tools=tools, exc=exc)
                    continue
                # If only 1 key is available, don't sleep in unit tests with cooldown duration 0
                _note_tpd(model, exc)
                cooldown_dur = self.key_pool.cooldown_seconds
                if len(self.key_pool.keys) <= 1 and cooldown_dur > 0:
                    time.sleep(min(3, cooldown_dur))
                self.key_pool.cooldown(api_key, duration=cooldown_dur if cooldown_dur == 0 else (5.0 if len(self.key_pool.keys) <= 1 else None))
                key_attempts += 1
                if self.emitter:
                    self.emitter.emit("retry", "groq", step=step, status="key_cooldown_429",
                                      detail={"key_id": KeyPool.mask_key(api_key),
                                              "attempt": key_attempts,
                                              "message": _error_message(exc)[:300]})
                continue
            except APIStatusError as exc:
                # APIStatusError yang tembus dari retryer (misalnya rate limit 429 atau upstream timeout dari Groq)
                status_code = getattr(exc, "status_code", 0)
                if _is_tool_call_error(exc):
                    # Model kadang salah menyebut nama tool; satu kali ulang biasanya sudah benar.
                    if tool_retries < 1:
                        tool_retries += 1
                        if self.emitter:
                            self.emitter.emit("retry", "groq", step=step, status="tool_call_retry",
                                              detail={"model": model, "attempt": tool_retries,
                                                      "message": _error_message(exc)[:250]})
                        continue
                    raise ToolCallInvalid(
                        f"Model '{model}' mengirim tool call yang ditolak Groq: {_error_message(exc)[:200]}")
                if status_code == 404 and "does not exist" in _error_message(exc).lower():
                    raise ModelUnavailable(f"Model '{model}' tidak tersedia di Groq.")
                if _is_request_too_large(exc):
                    # 413 dari Groq: bukan error sementara dan tidak tergantung kunci.
                    # Satu kali percobaan ulang dengan prompt+output lebih kecil, lalu berhenti.
                    if too_large_retry:
                        raise self._too_large_error(model, exc) from None
                    too_large_retry = True
                    messages, arguments = self._shrink_after_413(
                        messages, arguments, model=model, step=step, tools=tools, exc=exc)
                    continue
                if status_code in (429, 500, 502, 503, 520, 524):
                    _note_tpd(model, exc)
                    self.key_pool.cooldown(api_key, duration=self.key_pool.cooldown_seconds or 5.0)
                    key_attempts += 1
                    if self.emitter:
                        self.emitter.emit("retry", "groq", step=step, status=f"key_cooldown_{status_code}",
                                          detail={"key_id": KeyPool.mask_key(api_key),
                                                  "status_code": status_code,
                                                  "attempt": key_attempts,
                                                  "message": _error_message(exc)[:300]})
                    continue
                if self.emitter:
                    self.emitter.emit("error", "llm_request", step=step, status="failed",
                                      detail={"model": model, "error_type": "APIStatusError",
                                              "status_code": status_code,
                                              "message": str(exc)[:300],
                                              "key_id": KeyPool.mask_key(api_key)})
                raise RuntimeError(f"LLM request failed (APIStatusError: {status_code} - {_error_message(exc)[:200]})") from None
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

    def _too_large_error(self, model: str, exc: BaseException) -> RequestTooLarge:
        """Ubah error 413 penyedia menjadi pesan Indonesia yang bisa ditindaklanjuti."""
        limit, requested = _tpm_numbers(exc)
        message = too_large_message(model, limit=limit, requested=requested)
        if self.emitter:
            self.emitter.emit("error", "llm_request", step="llm", status="request_too_large",
                              detail={"model": model, "tpm_limit": limit, "requested_tokens": requested,
                                      "message": message})
        return RequestTooLarge(message)

    def _shrink_after_413(self, messages: list[dict[str, Any]], arguments: dict[str, Any], *,
                          model: str, step: str, tools: list[dict[str, Any]] | None,
                          exc: BaseException) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Satu percobaan pemulihan setelah 413: pangkas prompt lebih agresif + output lebih kecil.

        Batas yang dipakai diambil dari angka TPM di body error bila ada (itu kebenaran
        penyedia untuk akun ini), bukan dari batas yang di-hardcode.
        """
        limit, requested = _tpm_numbers(exc)
        current_output = int(arguments.get("max_completion_tokens") or token_budget.default_max_completion_tokens())
        # Kurangi output dulu (tidak mengurangi instruksi), maksimal 1/3 dari sebelumnya.
        new_output = max(256, min(current_output, int(current_output / 3) or 256))
        if requested and limit and requested > limit:
            overflow = requested - limit
            new_output = max(256, min(new_output, max(256, current_output - overflow)))
        arguments = {**arguments, "max_completion_tokens": new_output}

        budget = token_budget.prompt_budget(limit or self._limiter(model).limit_tpm, new_output)
        fitted, estimated, compacted = token_budget.fit_messages(messages, budget, tools=tools)
        if not compacted and budget <= 0:
            # Tanpa batas TPM yang diketahui, tetap potong separuh prompt terbesar sebagai upaya terakhir.
            half = token_budget.count_tokens(messages, tools) // 2
            fitted, estimated, compacted = token_budget.fit_messages(messages, half, tools=tools)
        if self.emitter:
            self.emitter.emit("warn", "token_budget", step=step, status="compacted_after_413",
                              tokens_in=estimated,
                              detail={"model": model, "provider_tpm_limit": limit,
                                      "provider_requested": requested,
                                      "max_completion_tokens": new_output,
                                      "prompt_budget": budget})
        return fitted, arguments

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
