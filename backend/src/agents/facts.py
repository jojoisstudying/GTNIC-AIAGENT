"""Fakta bersumber untuk planner: research.facts.stats dan research.facts.quotes.

PRINSIP (kejujuran, ditegakkan di KODE, bukan di prompt):
- Angka dan kutipan TIDAK PERNAH ditulis model. Sumbernya hanya dua:
  (a) brand.verified_facts  : dikurasi pemilik akun (dipercaya, hanya divalidasi bentuknya), dan
  (b) teks hasil tool       : diekstrak KODE secara verbatim (regex), lengkap dengan kalimat buktinya.
- Model hanya (1) menilai relevansi kandidat terhadap topik dan (2) menulis label Indonesia untuk statistik.
  Nilai angka, kalimat bukti, dan teks kutipan selalu diambil dari kandidat, bukan dari jawaban model.
- Gagal tertutup: bila model tidak tersedia / jawabannya tidak valid, fakta dari web TIDAK dipakai.

Bentuk keluaran (dibaca planner lewat research["facts"]):
  {"stats":  [{"value","label","source","source_url","evidence","origin"}],
   "quotes": [{"text","name","source","source_url","origin"}]}
Batas panjang mengikuti schema layout data_angka_besar / data_tiga_angka / bukti_kutipan.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

MAX_STATS = 6
MAX_QUOTES = 3
MAX_STAT_CANDIDATES = 12
MAX_QUOTE_CANDIDATES = 6

VALUE_MAX = 6                      # data_tiga_angka.value_N (data_angka_besar longgar sampai 8)
LABEL_MIN, LABEL_MAX = 8, 44       # irisan data_angka_besar (8-60) dan data_tiga_angka (6-44)
SOURCE_MIN, SOURCE_MAX = 3, 64
QUOTE_MIN, QUOTE_MAX = 30, 150
NAME_MIN, NAME_MAX = 3, 32
QSOURCE_MAX = 48

_SITE_NAMES = {"later.com": "Later", "buffer.com": "Buffer", "sproutsocial.com": "Sprout Social",
               "hootsuite.com": "Hootsuite"}
# Kata pembatas di depan angka mengubah makna ("up to 80%"): kandidat seperti itu dibuang, bukan ditafsirkan.
_QUALIFIER = re.compile(r"(?:up to|upto|over|more than|less than|fewer than|nearly|almost|around|about|roughly|"
                        r"approximately|at least|at most|under|as much as|as many as)\s*$", re.I)
_STAT = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{1,2})?)(%|[x×])(?![A-Za-z0-9%])")
_NAME = r"[A-Z][\w'.-]+(?:\s[A-Z][\w'.-]+){1,2}"
_VERBS = r"(?:said|says|explains|explained|notes|noted|adds|added)"
_QUOTE_A = re.compile(r'"([^"]{%d,%d})"\s*,?\s*%s\s+(%s)(?:,\s*([^.",]{3,60}))?' % (QUOTE_MIN, QUOTE_MAX + 2, _VERBS, _NAME))
_QUOTE_B = re.compile(r'(%s)(?:,\s*([^,"]{3,50}),)?\s+%s[,:]?\s*"([^"]{%d,%d})"' % (_NAME, _VERBS, QUOTE_MIN, QUOTE_MAX + 2))
_BAD_NAME_START = {"The", "This", "That", "These", "According", "Instagram", "TikTok", "Later", "Buffer", "Hootsuite",
                   "Sprout", "Meta", "Facebook", "LinkedIn", "YouTube", "However", "While", "When"}


# ---------------------------------------------------------------- util

def _norm(text) -> str:
    s = str(text or "")
    for a, b in (("\u201c", '"'), ("\u201d", '"'), ("\u2019", "'"), ("\u2018", "'"), ("\u00a0", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _json_object(text: str):
    text = (text or "").strip()
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[m.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def source_label(url: str, published: str | None = None) -> str:
    host = (urlparse(url or "").hostname or "").lower().removeprefix("www.")
    name = next((v for k, v in _SITE_NAMES.items() if host == k or host.endswith("." + k)), host or "sumber")
    year = re.search(r"(20\d\d)", str(published or ""))
    return (f"{name} ({year.group(1)})" if year else name)[:SOURCE_MAX]


def _snippets(gathered: list):
    for g in gathered or []:
        if g.get("tool") != "search_social_trends":
            continue
        for r in (g.get("result") or {}).get("results", []) or []:
            if isinstance(r, dict) and r.get("url") and r.get("content"):
                yield r


# ---------------------------------------------------------------- kandidat (KODE, verbatim)

def candidate_stats(gathered: list) -> list[dict]:
    """Statistik % / kelipatan (3x) dari kalimat sumber. Nilai = teks persis di sumber."""
    out, seen = [], set()
    for r in _snippets(gathered):
        text = _norm(r["content"])
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if not 20 <= len(sentence) <= 320:
                continue
            for m in _STAT.finditer(sentence):
                if _QUALIFIER.search(sentence[:m.start()][-16:]):
                    continue
                value = m.group(1) + m.group(2)
                if len(value) > VALUE_MAX or value not in sentence:
                    continue
                key = (value, r["url"], sentence)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"value": value, "sentence": sentence, "source_url": r["url"],
                            "source": source_label(r["url"], r.get("published"))})
    for i, c in enumerate(out[:MAX_STAT_CANDIDATES]):
        c["id"] = i
    return out[:MAX_STAT_CANDIDATES]


def candidate_quotes(gathered: list) -> list[dict]:
    """Kutipan orang bernama: teks di dalam tanda kutip + atribusi 'said/says ...'. Teks tidak pernah diubah."""
    out, seen = [], set()
    for r in _snippets(gathered):
        text = _norm(r["content"])
        found = []
        for m in _QUOTE_A.finditer(text):
            found.append((m.group(1), m.group(2), m.group(3)))
        for m in _QUOTE_B.finditer(text):
            found.append((m.group(3), m.group(1), m.group(2)))
        for quote, name, role in found:
            quote = quote.strip().rstrip(",;").strip()
            name = (name or "").strip()
            if not QUOTE_MIN <= len(quote) <= QUOTE_MAX or not NAME_MIN <= len(name) <= NAME_MAX:
                continue
            if name.split()[0] in _BAD_NAME_START or len(quote.split()) < 5 or quote.isupper():
                continue
            if quote not in text or name not in text or quote in seen:     # bukti verbatim
                continue
            seen.add(quote)
            role = (role or "").strip()
            src = role if SOURCE_MIN <= len(role) <= QSOURCE_MAX else source_label(r["url"], r.get("published"))
            out.append({"text": quote, "name": name, "source": src[:QSOURCE_MAX], "source_url": r["url"]})
    for i, c in enumerate(out[:MAX_QUOTE_CANDIDATES]):
        c["id"] = i
    return out[:MAX_QUOTE_CANDIDATES]


# ---------------------------------------------------------------- penilaian model (relevansi + label)

SYSTEM = ("Kamu pemeriksa kandidat fakta yang ketat. Kamu TIDAK boleh menulis angka atau kutipan baru; kamu hanya menilai "
          "kandidat yang diberikan. Balas HANYA dengan JSON valid.")


def build_prompt(topic: str, stats: list[dict], quotes: list[dict]) -> str:
    return (
        f"Topik posting: {topic}\n\n"
        "Untuk tiap kandidat, putuskan keep=true HANYA jika:\n"
        "(a) kalimat sumber menyatakan fakta yang jelas dan berdiri sendiri (subjek dan hal yang diukur jelas), dan\n"
        "(b) relevan untuk topik posting atau audiensnya. Fakta yang hanya soal teknik media sosial TIDAK relevan "
        "kecuali topiknya memang tentang media sosial.\n"
        f"Untuk statistik, tulis label bahasa Indonesia {LABEL_MIN}-{LABEL_MAX} karakter: jelaskan APA yang diukur dan "
        "arahnya (naik/turun/sebagian dari ...), tanpa angka apa pun, tanpa menambah klaim di luar kalimat sumber.\n\n"
        f"KANDIDAT STATISTIK: {json.dumps([{k: c[k] for k in ('id', 'value', 'sentence')} for c in stats], ensure_ascii=False)}\n"
        f"KANDIDAT KUTIPAN: {json.dumps([{k: c[k] for k in ('id', 'text', 'name')} for c in quotes], ensure_ascii=False)}\n\n"
        'Format: {"stats":[{"id":0,"keep":true,"label":""}],"quotes":[{"id":0,"keep":true}]}'
    )


def apply_judgement(stats: list[dict], quotes: list[dict], judged: dict) -> tuple[list[dict], list[dict], list[str]]:
    """Gabungkan penilaian model dengan kandidat. Nilai/kalimat bukti/teks kutipan SELALU dari kandidat."""
    warnings, out_s, out_q = [], [], []
    by_s, by_q = {c["id"]: c for c in stats}, {c["id"]: c for c in quotes}
    for item in (judged or {}).get("stats", []) or []:
        c = by_s.get(item.get("id")) if isinstance(item, dict) else None
        if not c or item.get("keep") is not True:
            continue
        label = _norm(item.get("label"))
        if not LABEL_MIN <= len(label) <= LABEL_MAX or re.search(r"\d", label):
            warnings.append(f"Label statistik {c['value']} dibuang (panjang/angka tidak valid).")
            continue
        out_s.append({"value": c["value"], "label": label, "source": c["source"], "source_url": c["source_url"],
                      "evidence": c["sentence"], "origin": "web"})
    for item in (judged or {}).get("quotes", []) or []:
        c = by_q.get(item.get("id")) if isinstance(item, dict) else None
        if c and item.get("keep") is True:
            out_q.append({"text": c["text"], "name": c["name"], "source": c["source"],
                          "source_url": c["source_url"], "origin": "web"})
    return out_s, out_q, warnings


def extract_web_facts(topic: str, gathered: list, ask) -> tuple[list[dict], list[dict], list[str]]:
    """`ask(system, user) -> str` memanggil model. Gagal tertutup bila model tidak menjawab dengan benar."""
    stats, quotes = candidate_stats(gathered), candidate_quotes(gathered)
    if not stats and not quotes:
        return [], [], []
    try:
        judged = _json_object(ask(SYSTEM, build_prompt(topic, stats, quotes)))
    except Exception as e:                                   # noqa: BLE001 - riset tetap jalan tanpa fakta web
        return [], [], [f"Penilaian fakta web gagal ({type(e).__name__}); fakta web tidak dipakai."]
    if judged is None:
        return [], [], ["Jawaban penilaian fakta bukan JSON valid; fakta web tidak dipakai."]
    return apply_judgement(stats, quotes, judged)


# ---------------------------------------------------------------- fakta pemilik (brand.verified_facts)

def clean_brand_facts(raw) -> tuple[dict, list[str]]:
    """Validasi BENTUK saja (pemilik dipercaya): item yang tidak muat di layout dibuang dengan peringatan."""
    warnings, stats, quotes = [], [], []
    raw = raw if isinstance(raw, dict) else {}
    for i, s in enumerate(raw.get("stats", []) or []):
        if not isinstance(s, dict):
            warnings.append(f"verified_facts.stats[{i}] bukan objek."); continue
        value, label, source = (_norm(s.get(k)) for k in ("value", "label", "source"))
        if not (1 <= len(value) <= VALUE_MAX and LABEL_MIN <= len(label) <= LABEL_MAX
                and SOURCE_MIN <= len(source) <= SOURCE_MAX):
            warnings.append(f"verified_facts.stats[{i}] dibuang: value 1-{VALUE_MAX}, label {LABEL_MIN}-{LABEL_MAX}, "
                            f"source {SOURCE_MIN}-{SOURCE_MAX} karakter.")
            continue
        stats.append({"value": value, "label": label, "source": source, "origin": "brand"})
    for i, q in enumerate(raw.get("quotes", []) or []):
        if not isinstance(q, dict):
            warnings.append(f"verified_facts.quotes[{i}] bukan objek."); continue
        text, name, source = (_norm(q.get(k)) for k in ("text", "name", "source"))
        if not (QUOTE_MIN <= len(text) <= QUOTE_MAX and NAME_MIN <= len(name) <= NAME_MAX and len(source) <= QSOURCE_MAX):
            warnings.append(f"verified_facts.quotes[{i}] dibuang: text {QUOTE_MIN}-{QUOTE_MAX}, name {NAME_MIN}-{NAME_MAX}, "
                            f"source maks {QSOURCE_MAX} karakter.")
            continue
        quotes.append({"text": text, "name": name, "source": source, "origin": "brand"})
    return {"stats": stats, "quotes": quotes}, warnings


def build_facts(topic: str, gathered: list, brand_facts, ask) -> tuple[dict, list[str]]:
    """Fakta pemilik lebih dulu (paling tepercaya), lalu fakta web yang lolos penilaian. Tanpa duplikat."""
    facts, warnings = clean_brand_facts(brand_facts)
    web_s, web_q, w = extract_web_facts(topic, gathered, ask)
    warnings += w
    seen_v = {(s["value"], _norm(s["label"]).lower()) for s in facts["stats"]}
    for s in web_s:
        if (s["value"], s["label"].lower()) not in seen_v:
            facts["stats"].append(s)
            seen_v.add((s["value"], s["label"].lower()))
    seen_q = {_norm(q["text"]).lower() for q in facts["quotes"]}
    for q in web_q:
        if _norm(q["text"]).lower() not in seen_q:
            facts["quotes"].append(q)
            seen_q.add(_norm(q["text"]).lower())
    facts["stats"], facts["quotes"] = facts["stats"][:MAX_STATS], facts["quotes"][:MAX_QUOTES]
    return facts, warnings
