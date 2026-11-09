"""Manajemen anggaran token LLM: estimasi, kompaksi konteks, dan throttle TPM.

Dipisah dari ``llm.py`` supaya bisa dipakai juga oleh prompt builder (planner,
scriptwriter) dan diuji tanpa memanggil jaringan.

Semua batas dibaca dari env lewat :mod:`src.config`; tidak ada angka TPM yang
di-hardcode di dalam logika:

- ``LLM_TPM_LIMIT``            batas token/menit default untuk semua model.
- ``LLM_TPM_LIMITS``           override per model, format ``model=limit,model=limit``.
- ``LLM_TPM_SAFETY_RATIO``     porsi batas yang boleh dipakai (default 0.92).
- ``LLM_MAX_COMPLETION_TOKENS`` batas token output default (default 2048).
- ``LLM_CHARS_PER_TOKEN``      rasio estimasi karakter/token (default 2.8, konservatif).
- ``LLM_TPM_MAX_WAIT``         detik maksimum menunggu throttle (default 20).
"""
from __future__ import annotations

import json
import time
from collections import deque
from typing import Any, Iterable

from src import config
from src.carousel.sources import URL_RE

DEFAULT_CHARS_PER_TOKEN = 2.8     # diukur dari error nyata Groq: ~19.1k karakter -> ~6.5k token
DEFAULT_MAX_COMPLETION_TOKENS = 2560
DEFAULT_SAFETY_RATIO = 0.92
DEFAULT_MAX_WAIT_SECONDS = 60.0
COMPACT_MARK = "\n…[dipotong otomatis agar hemat token]…\n"

# Prioritas pemangkasan: konteks yang paling boleh dikorbankan lebih dulu.
_PRIORITY = {"tool": 0, "assistant": 1, "user": 2, "system": 3}


def chars_per_token() -> float:
    try:
        value = float(config.opt("LLM_CHARS_PER_TOKEN", str(DEFAULT_CHARS_PER_TOKEN)))
    except ValueError:
        return DEFAULT_CHARS_PER_TOKEN
    return value if value > 0 else DEFAULT_CHARS_PER_TOKEN


def estimate_tokens(value: Any) -> int:
    """Estimasi token dari teks/objek apa pun (konservatif, sengaja dibulatkan ke atas)."""
    if value is None:
        return 0
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return int(len(value) / chars_per_token()) + 1


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = " ".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content)
    else:
        text = "" if content is None else str(content)
    tool_calls = message.get("tool_calls")
    if tool_calls:
        text += json.dumps(tool_calls, ensure_ascii=False, separators=(",", ":"), default=str)
    return text


def count_tokens(messages: Iterable[dict[str, Any]], tools: Any = None) -> int:
    """Estimasi total token satu request chat (messages + skema tools + overhead)."""
    total = 0
    for message in messages or []:
        total += estimate_tokens(_message_text(message)) + 4      # overhead role/format per pesan
    if tools:
        total += estimate_tokens(tools)
    return total


def _replace_text(message: dict[str, Any], new_text: str) -> dict[str, Any]:
    updated = dict(message)
    content = updated.get("content")
    if isinstance(content, list):
        updated["content"] = [{"type": "text", "text": new_text}]
    else:
        updated["content"] = new_text
    return updated


def _shrink_text(text: str, keep: int) -> str:
    """Ambil bagian awal + akhir supaya instruksi pembuka dan penutup tetap terlihat."""
    if keep <= 0:
        return ""
    if len(text) <= keep:
        return text
    head = int(keep * 0.55)
    tail = max(keep - head, 0)
    body = text[:head] + COMPACT_MARK + (text[-tail:] if tail else "")
    return body


def fit_messages(messages: list[dict[str, Any]], max_prompt_tokens: int, *,
                 tools: Any = None) -> tuple[list[dict[str, Any]], int, bool]:
    """Pangkas isi pesan sampai estimasi token <= ``max_prompt_tokens``.

    Aturan: pesan ``tool`` dan ``assistant`` lama dipangkas lebih dulu, lalu ``user``
    lama, dan pesan terakhir baru disentuh setelah pilihan lain habis. ``system``
    tidak dipangkas selama masih ada kandidat lain (instruksi inti tetap utuh).

    Returns: (messages, estimated_tokens, was_compacted)
    """
    current = count_tokens(messages, tools)
    if max_prompt_tokens <= 0 or current <= max_prompt_tokens:
        return messages, current, False

    msgs = [dict(m) for m in messages]
    compacted = False
    for _ in range(24):
        if current <= max_prompt_tokens:
            break
        excess_chars = int((current - max_prompt_tokens) * chars_per_token()) + 64
        candidates = []
        for index, message in enumerate(msgs):
            text = _message_text(message)
            role = str(message.get("role") or "user")
            if not text:
                continue
            # pesan terakhir adalah instruksi tugas: diperlakukan paling akhir
            last_bonus = 1 if index == len(msgs) - 1 else 0
            candidates.append((_PRIORITY.get(role, 2) + last_bonus, -len(text), index, text))
        if not candidates:
            break
        candidates.sort()
        _, neg_len, index, text = candidates[0]
        keep = max(len(text) - excess_chars, 0)
        if keep >= len(text):
            break
        trimmed = _shrink_text(text, keep)
        if trimmed == text:
            break
        msgs[index] = _replace_text(msgs[index], trimmed)
        compacted = True
        current = count_tokens(msgs, tools)
    return msgs, current, compacted


def tpm_limit(model: str | None = None) -> int:
    """Batas token/menit untuk model (0 = tidak dibatasi)."""
    raw_map = (config.opt("LLM_TPM_LIMITS", "") or "").strip()
    if model and raw_map:
        for entry in raw_map.split(","):
            name, _, value = entry.partition("=")
            if name.strip() == model:
                try:
                    return max(0, int(float(value.strip())))
                except ValueError:
                    break
    try:
        return max(0, int(float(config.opt("LLM_TPM_LIMIT", "0") or 0)))
    except ValueError:
        return 0


def safety_ratio() -> float:
    try:
        ratio = float(config.opt("LLM_TPM_SAFETY_RATIO", str(DEFAULT_SAFETY_RATIO)))
    except ValueError:
        return DEFAULT_SAFETY_RATIO
    return min(max(ratio, 0.1), 1.0)


def truncate_values(node: Any, max_chars: int = 400, depth: int = 0) -> Any:
    """Potong nilai string panjang di dalam struktur JSON tanpa merusak bentuknya.

    Dipakai untuk mengecilkan konteks (riset, brand) sebelum masuk prompt: kunci
    tetap ada, hanya isi yang kepanjangan dipangkas di ujung.

    URL TIDAK PERNAH dipotong. Model menyalin URL apa adanya ke ``research_used``;
    URL setengah jadi (``https://later.com/blog/instag…``) akan ditolak validator
    sumber karena tidak sama dengan URL asli di riset. Lebih baik kelebihan beberapa
    token daripada kehilangan seluruh run karena referensi tidak cocok.
    """
    if max_chars <= 0 or depth > 12:
        return node
    if isinstance(node, str):
        if len(node) <= max_chars:
            return node
        if URL_RE.fullmatch(node.strip()):
            return node
        # Teks yang berisi URL: pangkas di sekitar URL utuh, jangan memotong di tengah URL.
        if URL_RE.search(node):
            return _truncate_around_urls(node, max_chars)
        return node[: max_chars - 1].rstrip() + "…"
    if isinstance(node, dict):
        return {k: truncate_values(v, max_chars, depth + 1) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [truncate_values(v, max_chars, depth + 1) for v in node]
    return node


def _truncate_around_urls(text: str, max_chars: int) -> str:
    """Pangkas teks yang memuat URL tanpa memotong URL-nya.

    URL boleh membuat hasil sedikit melebihi ``max_chars``: kelebihan beberapa karakter
    jauh lebih murah daripada URL setengah jadi yang ditolak validator sumber.
    """
    urls = [m.group(0) for m in URL_RE.finditer(text)]
    if not urls:
        return text[: max_chars - 1].rstrip() + "…"
    longest = max(urls, key=len)
    head_budget = max_chars - len(longest) - 2
    head = text.split(longest, 1)[0].rstrip()
    if head_budget <= 0:
        return longest
    return f"{head[:head_budget].rstrip()}…{longest}" if head else longest


def clip_text(value: Any, max_chars: int) -> str:
    """Potong teks ke ``max_chars`` TANPA pernah memotong URL di dalamnya.

    Dipakai semua tempat yang menyiapkan konteks untuk model: begitu URL terpotong
    (``…/instag…``), model menyalinnya utuh ke ``research_used`` dan validator sumber
    menolaknya sebagai referensi karangan.
    """
    text = str(value or "")
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    if URL_RE.fullmatch(text.strip()):
        return text
    if URL_RE.search(text):
        return _truncate_around_urls(text, max_chars)
    return text[: max_chars - 1].rstrip() + "…"


def default_max_completion_tokens() -> int:
    try:
        value = int(float(config.opt("LLM_MAX_COMPLETION_TOKENS", str(DEFAULT_MAX_COMPLETION_TOKENS))))
    except ValueError:
        return DEFAULT_MAX_COMPLETION_TOKENS
    return max(256, value)


def prompt_budget(limit_tpm: int, max_completion_tokens: int) -> int:
    """Token prompt yang boleh dikirim: batas TPM setelah reservasi output (0 = tanpa batas)."""
    if limit_tpm <= 0:
        return 0
    usable = int(limit_tpm * safety_ratio())
    return max(usable - max_completion_tokens, 0)


class TokenRateLimiter:
    """Jendela geser 60 detik: tahan request bila kuota menit ini hampir habis.

    Groq menghitung TPM dari prompt + completion yang diminta, jadi kedua angka ikut
    dicatat. Tanpa limiter, satu run bisa menghabiskan 8.000 TPM lalu request
    berikutnya langsung ditolak 413/429 walau prompt-nya kecil.
    """

    def __init__(self, limit_tpm: int = 0, *, window_seconds: float = 60.0,
                 max_wait_seconds: float | None = None) -> None:
        self.limit_tpm = max(0, int(limit_tpm))
        self.window_seconds = window_seconds
        if max_wait_seconds is None:
            try:
                max_wait_seconds = float(config.opt("LLM_TPM_MAX_WAIT", str(DEFAULT_MAX_WAIT_SECONDS)))
            except ValueError:
                max_wait_seconds = DEFAULT_MAX_WAIT_SECONDS
        self.max_wait_seconds = max(0.0, max_wait_seconds)
        self._events: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= self.window_seconds:
            self._events.popleft()

    def used(self) -> int:
        self._prune(time.monotonic())
        return sum(tokens for _, tokens in self._events)

    def record(self, tokens: int) -> None:
        if self.limit_tpm <= 0 or tokens <= 0:
            return
        self._events.append((time.monotonic(), int(tokens)))

    def delay_for(self, tokens: int) -> float:
        """Berapa detik harus menunggu sebelum request sebesar ``tokens`` aman dikirim."""
        if self.limit_tpm <= 0 or tokens <= 0:
            return 0.0
        now = time.monotonic()
        self._prune(now)
        budget = int(self.limit_tpm * safety_ratio())
        # Buang pemakaian terlama sampai request ini muat (paling cepat: tunggu jendela penuh).
        events = list(self._events)
        used = sum(t for _, t in events)
        if used + tokens <= budget:
            return 0.0
        wait = 0.0
        for stamp, used_tokens in events:
            used -= used_tokens
            wait = max(wait, stamp + self.window_seconds - now)
            if used + tokens <= budget:
                break
        return max(wait, 0.0)

    def wait(self, tokens: int) -> float:
        """Blokir (maks ``max_wait_seconds``) sampai kuota menit cukup. Return detik ditunggu."""
        delay = self.delay_for(tokens)
        if delay <= 0:
            return 0.0
        slept = min(delay, self.max_wait_seconds)
        if slept > 0:
            time.sleep(slept)
        return slept

    def reset(self) -> None:
        self._events.clear()


# Kuota TPM melekat pada akun/kunci penyedia, bukan pada satu run. Beberapa run
# (carousel + reels, atau dua operator) bisa berjalan bersamaan di proses yang sama;
# tanpa limiter bersama, masing-masing mengira masih punya kuota penuh lalu dua-duanya
# ditolak 413. Registry ini memakai satu limiter per (model, batas) agar pemakaian
# dihitung gabungan.
_SHARED_LIMITERS: dict[tuple[str, int], TokenRateLimiter] = {}


def shared_limiter(model: str, limit_tpm: int) -> TokenRateLimiter:
    """Limiter proses-wide untuk ``model`` dengan batas ``limit_tpm`` (0 = tanpa batas)."""
    key = (model or "", max(0, int(limit_tpm or 0)))
    limiter = _SHARED_LIMITERS.get(key)
    if limiter is None:
        limiter = TokenRateLimiter(key[1])
        _SHARED_LIMITERS[key] = limiter
    return limiter


def reset_shared_limiters() -> None:
    """Buang semua limiter bersama (dipakai test dan setelah ganti API key/batas)."""
    _SHARED_LIMITERS.clear()
