"""Katalog sumber riset: normalisasi URL, ekstraksi, dan resolusi referensi.

Dipisah dari ``planner.py`` karena aturan "referensi harus berasal dari riset" dipakai
di dua tempat: saat menyusun prompt (daftar id sumber yang boleh dirujuk) dan saat
memvalidasi ``research_used``. Keduanya wajib memakai katalog yang sama, kalau tidak
model bisa dirujuk ke URL yang tidak pernah ia lihat.

Aturan normalisasi (sengaja konservatif supaya artikel berbeda tidak dianggap sama):

- Diambil URL-nya saja: teks Markdown ``[label](url)``, wrapper ``<url>``, dan tanda
  baca penutup (``.``, ``,``, ``;``, ``)`` …) dibuang.
- Skema dan host di-lowercase, ``www.`` dibuang, port default dibuang.
- Persen-encoding hanya didekode untuk karakter *unreserved* (A-Z a-z 0-9 - . _ ~),
  jadi ``%2F`` tidak berubah menjadi ``/`` (itu bisa menyatukan dua artikel berbeda).
- Fragment (``#...``) dibuang; parameter pelacakan (utm_*, fbclid, gclid, …) dibuang;
  sisa query diurutkan agar ``?a=1&b=2`` dan ``?b=2&a=1`` sama.
- Garis miring di akhir path dibuang (``/artikel/`` = ``/artikel``), tapi path tetap
  dipertahankan utuh sehingga dua artikel berbeda tidak pernah dianggap identik.
- http dan https dianggap lokasi yang sama *untuk keperluan pencocokan*; URL kanonik
  yang dipakai di output tetap URL yang ditemukan di riset.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

URL_RE = re.compile(r"https?://[^\s\"'<>\[\]{}|\\^`]+", re.IGNORECASE)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*(https?://[^)\s]+)\s*\)", re.IGNORECASE)
_PERCENT_RE = re.compile(r"%([0-9A-Fa-f]{2})")
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_TRAILING_PUNCT = ".,;:!?\"'"
# Parameter yang tidak pernah mengubah artikel yang dirujuk.
_TRACKING_PARAMS = frozenset({
    "fbclid", "gclid", "dclid", "msclkid", "igshid", "igsh", "mc_cid", "mc_eid",
    "ref", "ref_src", "ref_url", "source", "s", "share", "share_id",
})
_DEFAULT_PORTS = {"http": "80", "https": "443"}


def _decode_unreserved(value: str) -> str:
    """Dekode hanya karakter unreserved (``%41`` -> ``A``), biarkan sisanya apa adanya."""
    def repl(match: re.Match) -> str:
        char = chr(int(match.group(1), 16))
        return char if char in _UNRESERVED else "%" + match.group(1).upper()
    return _PERCENT_RE.sub(repl, value)


def clean_url_text(value: object) -> str | None:
    """Ambil satu URL bersih dari string mentah (Markdown, wrapper, tanda baca)."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    md = MARKDOWN_LINK_RE.search(text)
    if md:
        text = md.group(1)
    else:
        found = URL_RE.search(text)
        if not found:
            return None
        text = found.group(0)
    # Tanda baca penutup kalimat bukan bagian URL.
    while text and text[-1] in _TRAILING_PUNCT:
        text = text[:-1]
    # Kurung tutup hanya dibuang bila tidak berpasangan (URL Wikipedia mis. tetap utuh).
    while text.endswith(")") and text.count("(") < text.count(")"):
        text = text[:-1].rstrip(_TRAILING_PUNCT)
    return text or None


def is_url_like(value: object) -> bool:
    """True bila string adalah URL (bukan teks biasa) — dipakai pemangkas token."""
    if not isinstance(value, str):
        return False
    return bool(URL_RE.fullmatch(value.strip()))


def normalize_url(value: object) -> str | None:
    """URL kanonik untuk perbandingan (tanpa skema), atau None bila bukan URL valid."""
    raw = clean_url_text(value)
    if not raw:
        return None
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        return None
    host = parts.netloc.lower()
    if "@" in host:                       # buang userinfo
        host = host.rsplit("@", 1)[1]
    scheme = parts.scheme.lower()
    if ":" in host:
        hostname, _, port = host.rpartition(":")
        if port.isdigit() and port != _DEFAULT_PORTS.get(scheme):
            host = f"{hostname}:{port}"
        elif port.isdigit():
            host = hostname
    if host.startswith("www."):
        host = host[4:]
    host = host.rstrip(".")
    path = _decode_unreserved(parts.path or "/")
    path = re.sub(r"/{2,}", "/", path) or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    query_pairs = []
    for chunk in (parts.query or "").split("&"):
        if not chunk:
            continue
        name, _, val = chunk.partition("=")
        if name.lower() in _TRACKING_PARAMS or name.lower().startswith("utm_"):
            continue
        query_pairs.append((_decode_unreserved(name), _decode_unreserved(val)))
    query_pairs.sort()
    query = "&".join(f"{n}={v}" if v else n for n, v in query_pairs)
    key = f"{host}{path}"
    if query:
        key += "?" + query
    return key


def extract_urls(node: object) -> list[str]:
    """Semua URL yang muncul di dalam struktur JSON (urutan kemunculan, duplikat dibiarkan)."""
    found: list[str] = []

    def walk(value):
        if isinstance(value, str):
            found.extend(m.group(0) for m in URL_RE.finditer(value))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(node)
    return found


@dataclass(frozen=True)
class Source:
    """Satu sumber riset: id stabil (S1, S2, …), URL asli, dan kunci normalisasinya."""
    id: str
    url: str
    key: str


class SourceCatalog:
    """Daftar sumber riset yang boleh dirujuk oleh ``research_used``."""

    def __init__(self, sources: list[Source]):
        self.sources = sources
        self._by_id = {s.id.lower(): s for s in sources}
        self._by_key = {s.key: s for s in sources}

    # ------------------------------------------------------------ pembuatan
    @classmethod
    def from_research(cls, research: object, *, limit: int = 0) -> "SourceCatalog":
        """Bangun katalog dari hasil riset.

        Urutan prioritas mengikuti cara planner memakai data: ``sources`` tingkat atas
        lebih dulu (paling sering dikutip), baru URL lain yang muncul di kedalaman
        struktur (``topic_candidates[].source_urls``, ``posting_time.source_urls``,
        ``trending_formats[].source_url``, teks kutipan).
        """
        ordered: list[str] = []
        seen: set[str] = set()

        def add(raw: object) -> None:
            clean = clean_url_text(raw)
            if not clean:
                return
            key = normalize_url(clean)
            if not key or key in seen:
                return
            seen.add(key)
            ordered.append(clean)

        top = (research or {}).get("sources") if isinstance(research, dict) else None
        for raw in top or []:
            add(raw)
        for raw in extract_urls(research):
            add(raw)
        if limit > 0:
            ordered = ordered[:limit]
        return cls([Source(f"S{i}", url, normalize_url(url) or url)
                    for i, url in enumerate(ordered, 1)])

    # ------------------------------------------------------------ akses
    def __len__(self) -> int:
        return len(self.sources)

    def __bool__(self) -> bool:
        return bool(self.sources)

    @property
    def urls(self) -> list[str]:
        return [s.url for s in self.sources]

    def keys(self) -> set[str]:
        return {s.key for s in self.sources}

    def get(self, ref: object) -> Source | None:
        """Cari sumber berdasarkan id (``S1``) atau URL (setelah normalisasi)."""
        if isinstance(ref, Source):
            return ref
        if not isinstance(ref, str):
            return None
        token = ref.strip()
        if not token:
            return None
        by_id = self._by_id.get(token.lower())
        if by_id is not None:
            return by_id
        key = normalize_url(token)
        if key and key in self._by_key:
            return self._by_key[key]
        return None

    def resolve(self, ref: object) -> str | None:
        """URL kanonik untuk ``ref``, termasuk koreksi aman, atau None bila tak dikenal.

        Koreksi aman hanya dilakukan kalau hasilnya *tunggal*: URL yang terpotong
        (diakhiri ``…``/``...``) dicocokkan sebagai awalan, dan query pelacakan
        diabaikan lewat normalisasi. Lebih dari satu kandidat = tidak dikoreksi,
        supaya URL karangan tidak pernah diterima.
        """
        found = self.get(ref)
        if found is not None:
            return found.url
        if not isinstance(ref, str):
            return None
        candidate = clean_url_text(ref) or ""
        truncated = candidate.endswith(("…", "...")) or ref.strip().endswith(("…", "..."))
        candidate = candidate.rstrip("…").rstrip(".").strip()
        key = normalize_url(candidate)
        if not key:
            return None
        # 1) cocok persis setelah normalisasi longgar (skema/host/trailing slash/query)
        if key in self._by_key:
            return self._by_key[key].url
        # 2) satu-satunya sumber yang diawali URL ini (kasus URL terpotong)
        if truncated:
            matches = [s for s in self.sources if s.key.startswith(key)]
            if len(matches) == 1:
                return matches[0].url
        # 3) URL ini adalah awalan dari tepat satu sumber, dan awalan itu cukup spesifik
        matches = [s for s in self.sources if s.key.startswith(key)]
        if len(matches) == 1 and len(key) >= max(12, int(len(matches[0].key) * 0.6)):
            return matches[0].url
        return None

    # ------------------------------------------------------------ prompt
    def prompt_block(self, limit: int = 8) -> str:
        """Daftar id + URL untuk ditempel di prompt (maks ``limit`` baris)."""
        if not self.sources:
            return ("(TIDAK ADA SUMBER URL pada riset ini. Isi research_used dengan [] "
                    "dan jangan menulis URL apa pun.)")
        rows = [f"{s.id} {s.url}" for s in self.sources[:limit]]
        if len(self.sources) > limit:
            rows.append(f"(+{len(self.sources) - limit} sumber lain ada di HASIL RISET; "
                        "rujuk lewat URL persis, bukan id)")
        return "\n".join(rows)
