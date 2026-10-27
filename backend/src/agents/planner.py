"""AGENT 2: Planner (Creative Director). Hasil riset Agent 1 + brand kit -> rencana 1 post (JSON).

Pembagian kerja:
- LLM  : konsep, copy (headline/subtext/slot), caption, jadwal.
- KODE : pemilihan layout final (variasi, anti-ulang, cooldown cover, kuota foto), pose, ikon,
         kata kunci CTA, style pack, kejujuran angka/klaim. Tidak ada id layout yang di-hardcode:
         semua keputusan dibaca dari metadata registry (role, density, needs_photo, tags).
Output divalidasi KODE; kalau melanggar aturan, planner diminta merevisi (maks MAX_ATTEMPTS).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter
from copy import deepcopy

from src import config
from src.layouts import validate_rhythm
from src.layouts import registry as layout_registry
from src.layouts.models import ROLES, validate_content
from src.layouts.primitives.icons import ICON_NAMES

MAX_ATTEMPTS = 3
ALLOWED_FORMATS = {"single_image", "carousel"}
MIN_CAROUSEL_SLIDES = 5
MAX_CAROUSEL_SLIDES = 6
HISTORY_POSTS = 6          # berapa rencana terakhir yang dipakai sebagai memori anti-ulang
COVER_COOLDOWN = 3         # layout cover yang sama tidak boleh muncul lagi dalam N post terakhir
MIN_PHOTO_SLIDES = 1       # carousel terasa personal: minimal 1 slide foto operator
MAX_PHOTO_SLIDES = 2       # ... tapi tidak lebih dari 2 supaya tidak monoton
MAX_EMPHASIS = 2           # aksen hemat: maksimal 2 frasa per slide
WHOLE_TEXT_RATIO = 0.7     # frasa yang menutupi >=70% judul bukan penekanan (selaras dengan renderer)
RETRY_TEMPERATURES = (0.7, 0.4, 0.3)
TZ_NOTE = "Zona waktu data riset belum terverifikasi dan belum dikonversi ke WIB. Perlakukan sebagai hipotesis, uji di akun sendiri."

CONTENT_ROLES = frozenset(r for r in ROLES if r not in {"cover", "cta"})
SLIDE_TO_LAYOUT_ROLES = {
    "cover": frozenset({"cover"}),
    "cta": frozenset({"cta"}),
    "single": frozenset({"cover", "cta"}),
    "content": CONTENT_ROLES,
}

# Janji hasil / klaim kesehatan yang tidak boleh muncul tanpa sumber (heuristik, bukan jaminan).
CLAIM_PATTERNS = [
    r"\bterbukti\b", r"\bdijamin\b", r"\bpasti\b", r"\bmengurangi\b", r"\bmenurunkan\b",
    r"\bmencegah\b", r"\bmenyembuhkan\b", r"\bkelelahan\b", r"\bstres\b",
    r"\bmeningkatkan (?:produktivitas|output|efisiensi|hasil|performa|fokus|kualitas)\b",
    r"\b(?:lebih|jauh lebih) (?:cepat|sehat|produktif)\b",
]

SYSTEM = "Kamu Creative Director social media untuk sebuah perusahaan. Output HANYA JSON valid, tanpa teks lain."

PROMPT = """BRAND KIT:
{brand}

TOPIK POSTING: {topic}

HASIL RISET (dari Agent 1):
{research}

Buat rencana SATU post Instagram dengan aturan berikut:
- Pipeline hanya menghasilkan GAMBAR statis: format "single_image" (1 slide, role "single") atau "carousel" (5-6 slide). Abaikan tren yang hanya berlaku untuk video kecuali bisa diterjemahkan jadi gambar.
- STRUKTUR CAROUSEL: slide pertama role "cover" (hook visual), 3-4 slide role "content" (substansi), slide terakhir role "cta".
- LAYOUT: setiap slide HARUS memakai id dari katalog di bawah (persis). Pilih berdasarkan FUNGSI isi slide (role, density, needs_photo, tags), bukan kebiasaan. Variasikan: jangan pakai layout yang sama berdekatan, dan jangan memaksakan pola yang sama dengan post sebelumnya. Role layout "cover" hanya untuk slide cover/single, role "cta" hanya untuk penutup, role lain untuk slide content.
- FOTO OPERATOR: brand punya figur operator. Buat carousel terasa personal dengan 1-2 slide berfoto (layout needs_photo "required"/"optional", isi pose_tags dari pose yang tercantum di layout itu dan ada di available_poses). Slide lain tanpa pose_tags. Jangan memakai foto lebih dari 2 slide.
- Setiap slide: headline maks 8 kata, subtext maks 22 kata. Untuk slide content, subtext berisi penjelasan substantif (idealnya 8-22 kata).
- pose_tags hanya dari available_poses. Jika butuh pose lain, isi new_pose_request dan pakai pose terdekat.
- KEJUJURAN: dilarang membuat angka/statistik yang tidak ada di riset/brand/topik. DILARANG janji hasil atau klaim kesehatan (mis. "mengurangi kelelahan", "meningkatkan produktivitas", "terbukti"). Tulis sebagai SARAN PRAKTIS ("Coba...", "Biasakan...", "Bisa dimulai dengan..."), bukan janji hasil.
- research_used: hanya URL yang tertulis di HASIL RISET (sources, source_url, source_urls). Salin persis, jangan mengarang URL.
- caption: kalimat pertama hook, isi singkat, lalu ajakan bertindak. Sesuai tone brand, tanpa janji hasil.
- hashtags: 3-8 buah, diawali #.
- schedule.slots: ambil waktu HANYA dari posting_time riset (tulis persis sebagaimana di riset). Waktu lain yang kamu usulkan sendiri boleh untuk A/B test, tapi akan diberi label "asumsi". ab_test: jelaskan perbandingan antar slot.
- "slots": isi semua field required layout terpilih (patuhi min/max karakter dan jumlah item). "params": hanya nilai enum yang valid. "emphasis": 1-2 frasa pendek yang benar-benar ada di slots (atau []).
- Layout ber-slot angka (value / value_1..3 + source) hanya boleh dipakai bila riset memberi angka bersumber (research.facts.stats); setiap value harus sama persis dengan salah satu stats. Layout ber-slot "quote" hanya bila riset memberi kutipan bersumber (research.facts.quotes), isi persis sama; jangan pernah mengarang angka, kutipan, atau testimoni. Jika datanya tidak ada, pilih layout lain.
- Layout ber-slot list: isi item yang benar-benar berbeda dan substantif; layout dua sisi: tiap sisi minimal 2 item. Jangan mengarang fakta demi mengisi slot.
- Layout CTA berbasis kata kunci komentar: "keyword" = SATU kata topik (bukan kata kerja seperti simpan/bagikan), ajakannya konsisten dengan komentar.
- Konten slots harus selaras dengan headline/subtext, bukan sekadar mengulang.
{variety}
KATALOG LAYOUT APPROVED (schema slots dan params):
{layout_catalog}
{issues}
Format JSON:
{{
 "concept": "1-2 kalimat",
 "content_pillar": "salah satu dari content_pillars",
 "format": "single_image | carousel",
 "slides": [{{"role": "cover|content|cta|single", "layout_id": "<id dari katalog>", "slots": {{}}, "params": {{}}, "emphasis": [], "headline": "", "subtext": "", "pose_tags": []}}],
 "caption": "",
 "hashtags": [],
 "schedule": {{"slots": [{{"time": ""}}], "rationale": "", "ab_test": ""}},
 "research_used": [],
 "new_pose_request": null
}}"""


# ---------------------------------------------------------------- util umum

def _words(s) -> int:
    return len(str(s or "").split())


def _nt(s: str) -> str:
    """Normalisasi teks waktu agar bisa dibandingkan."""
    return re.sub(r"[\s\-–—,.:()]", "", (s or "").lower())


def _json_object(text: str):
    """Ambil objek JSON pertama yang valid dari teks (tahan code fence & teks pembuka)."""
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


def _approved(root=None) -> dict:
    return {i: s for i, s in layout_registry.load_all(root).items() if s.meta.status == "approved"}


def _stats(research: dict) -> list:
    facts = (research or {}).get("facts") or {}
    stats = facts.get("stats", []) if isinstance(facts, dict) else []
    return [s for s in stats if isinstance(s, dict)]


def _quotes(research: dict) -> list[dict]:
    facts = (research or {}).get("facts") or {}
    quotes = facts.get("quotes", []) if isinstance(facts, dict) else []
    return [q for q in quotes if isinstance(q, dict) and str(q.get("text") or "").strip()]


def _value_slots(spec) -> list[str]:
    """Slot angka layout data: value, atau value_1..value_N (diurutkan)."""
    return sorted((n for n in spec.slots if re.fullmatch(r"value(_\d+)?", n)),
                  key=lambda n: int(n.split("_")[1]) if "_" in n else 0)


def _norm_text(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _text_of(value) -> str:
    return " ".join(map(str, value)) if isinstance(value, list) else str(value or "")


# ---------------------------------------------------------------- memori anti-ulang

def summarize_plan(plan: dict) -> dict:
    """Ringkas satu rencana jadi jejak visual (dipakai sebagai memori antar post)."""
    slides = [s for s in (plan or {}).get("slides") or [] if isinstance(s, dict)]
    return {
        "covers": [s.get("layout_id") for s in slides if s.get("role") in {"cover", "single"}],
        "content": [s.get("layout_id") for s in slides if s.get("role") == "content"],
        "cta": [s.get("layout_id") for s in slides if s.get("role") == "cta"],
        "poses": [t for s in slides for t in (s.get("pose_tags") or [])],
        "style": dict((plan or {}).get("style") or {}),
    }


def load_history(session=None, limit: int = HISTORY_POSTS, exclude_run: str | None = None) -> list[dict]:
    """Rencana ok terbaru (terbaru dulu) -> ringkasan. Sumber: DB bila ada, lalu output/runs/.
    Memori bersifat penasihat: error apa pun menghasilkan riwayat kosong, bukan kegagalan planner."""
    plans: list[dict] = []
    try:
        if session is not None:
            from sqlalchemy import select
            from src.core.db import Plan
            rows = session.scalars(select(Plan).where(Plan.ok.is_(True)).order_by(Plan.id.desc())
                                   .limit(limit * 3)).all()
            for row in rows:
                if exclude_run and row.run_id == exclude_run:
                    continue
                plan = json.loads(row.plan_json or "null")
                if isinstance(plan, dict) and plan.get("slides"):
                    plans.append(plan)
        if not plans:
            runs = config.OUTPUT_DIR / "runs"
            files = sorted(runs.glob("*/plan_v*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if runs.exists() else []
            for path in files:
                if exclude_run and path.parent.name == exclude_run:
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("ok") and isinstance(data.get("plan"), dict):
                    plans.append(data["plan"])
    except Exception:
        return []
    return [summarize_plan(p) for p in plans[:limit]]


def _usage(history: list[dict]) -> Counter:
    """Frekuensi layout di post terakhir; post lebih baru lebih berat."""
    usage: Counter = Counter()
    for k, h in enumerate(history or []):
        weight = 0.8 ** k
        for lid in (h.get("covers") or []) + (h.get("content") or []) + (h.get("cta") or []):
            if lid:
                usage[lid] += weight
    return usage


def _recent_covers(history: list[dict], approved: dict | None = None) -> set:
    """Cover yang masih 'cooldown'. Cooldown menyesuaikan jumlah layout cover yang ada: selalu
    menyisakan minimal satu pilihan (dengan 2 layout cover, hanya cover post terakhir yang diblokir)."""
    pool = {i for i, s in approved.items() if s.meta.role == "cover"} if approved else None
    limit = COVER_COOLDOWN if pool is None else min(COVER_COOLDOWN, max(len(pool) - 1, 0))
    seen: list[str] = []
    for h in history or []:
        for lid in h.get("covers") or []:
            if lid and lid not in seen and (pool is None or lid in pool):
                seen.append(lid)
        if len(seen) >= limit:
            break
    return set(seen[:limit])


def _variety_note(history: list[dict], approved: dict) -> str:
    if not history:
        return ""
    lines = ["\nMEMORI POST SEBELUMNYA (variasi antar post):"]
    covers = sorted(_recent_covers(history, approved))
    if covers:
        lines.append(f"- JANGAN pakai layout cover ini lagi (masih cooldown dari post terakhir): {', '.join(covers)}.")
    heavy = [f"{lid}({n:.1f})" for lid, n in _usage(history).most_common(4)
             if lid in approved and approved[lid].meta.role in CONTENT_ROLES]
    if heavy:
        lines.append(f"- Layout isi yang paling sering dipakai belakangan (hindari kecuali benar-benar paling cocok): {', '.join(heavy)}.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- katalog untuk prompt

def _layout_catalog_prompt(approved: dict | None = None) -> str:
    """Katalog ringkas (tanpa field kosong) agar hemat token."""
    approved = approved if approved is not None else _approved()
    catalog = []
    for spec in approved.values():
        slots = {}
        for name, s in spec.slots.items():
            d = {"type": s.type}
            for key in ("required", "min_chars", "max_chars", "min_items", "max_items", "item_max_chars"):
                v = getattr(s, key)
                if v:
                    d[key] = v
            slots[name] = d
        entry = {"id": spec.id, "role": spec.meta.role, "density": spec.meta.density,
                 "needs_photo": spec.meta.needs_photo, "slots": slots,
                 "params": {n: list(p.enum) for n, p in spec.params.items()}}
        if spec.meta.pose_tags:
            entry["pose_tags"] = list(spec.meta.pose_tags)
        if spec.meta.tags:
            entry["tags"] = list(spec.meta.tags)
        catalog.append(entry)
    return json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------- isi slot (tanpa mengarang fakta)

_STOPWORDS = {"yang", "untuk", "dengan", "dari", "dan", "atau", "pada", "dalam", "agar", "bisa", "anda", "kamu",
              "kita", "kami", "ini", "itu", "tips", "cara", "lebih", "setiap", "sebelum", "setelah", "mulai",
              "langkah", "praktis", "mudah", "singkat", "panduan"}
_ACTION_WORDS = {"simpan", "bagikan", "komen", "komentar", "ikuti", "share", "save", "follow", "klik", "ketik",
                 "tulis", "balas", "mulai"}
_CTA_VERBS = {"komen", "ketik", "tulis", "balas"}

_ICON_KEYWORDS = {
    "clock": ("waktu", "jam", "jadwal", "menit", "durasi", "rutin", "istirahat", "deadline", "tepat"),
    "shield": ("aman", "keselamatan", "k3", "apd", "lindung", "proteksi", "pelindung"),
    "alert": ("bahaya", "waspada", "hati-hati", "risiko", "peringatan", "kesalahan", "hindari", "darurat"),
    "users": ("tim", "rekan", "kolaborasi", "komunitas", "mentor", "teman", "atasan", "pewawancara", "budaya"),
    "doc": ("cv", "dokumen", "laporan", "portofolio", "surat", "catatan", "prosedur", "sop", "lamar", "formulir"),
    "chart": ("data", "angka", "statistik", "kinerja", "tren", "grafik", "evaluasi", "produktivitas"),
    "target": ("target", "tujuan", "prioritas", "sasaran", "rencana", "fokus"),
    "bulb": ("ide", "tips", "belajar", "pelajari", "kenali", "pahami", "inovasi", "kembangkan", "kreatif"),
    "check": ("pastikan", "cek", "periksa", "standar", "kualitas", "selesai", "benar"),
    "star": ("unggul", "terbaik", "prestasi", "nilai", "tunjukkan", "kemampuan", "bonus"),
}
_NEUTRAL_ICONS = ("bulb", "star", "target", "check", "doc")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9\-]*", (text or "").lower())


def _icon_scores(text: str) -> Counter:
    scores: Counter = Counter()
    toks = _tokens(text)
    for icon, kws in _ICON_KEYWORDS.items():
        if icon not in ICON_NAMES:
            continue
        for kw in kws:
            scores[icon] += sum(1 for t in toks if t == kw or (len(kw) >= 5 and t.startswith(kw)))
    return scores


def _pick_icon(text: str, current, used: set) -> str:
    """Ikon sesuai makna teks; hormati pilihan LLM yang valid, tapi 'alert' tanpa alasan dan duplikat diganti."""
    scores = _icon_scores(text)
    if current in ICON_NAMES and current not in used and (current != "alert" or scores["alert"] > 0):
        return current
    ranked = [i for i, n in scores.most_common() if n > 0 and i not in used]
    if ranked:
        return ranked[0]
    pool = [i for i in _NEUTRAL_ICONS if i in ICON_NAMES and i not in used] or [i for i in _NEUTRAL_ICONS if i in ICON_NAMES]
    h = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:6], 16)
    return pool[h % len(pool)]


def _keyword_from(*texts: str) -> str:
    """Satu kata topik dari teks pertama yang punya kandidat (urutan = prioritas)."""
    for text in texts:
        cands = [t for t in _tokens(text)
                 if 4 <= len(t) <= 12 and t.isalnum() and t not in _STOPWORDS and t not in _ACTION_WORDS]
        if cands:
            return cands[0].upper()
    return "INFO"


def _fit_text(value, slot) -> str:
    """Pangkas di batas kalimat bila melebihi max_chars (tanpa memotong di tengah kalimat)."""
    text = str(value or "").strip()
    if slot.type != "text" or not slot.max_chars or len(text) <= slot.max_chars:
        return text
    cut = text[:slot.max_chars]
    ends = [m.end() for m in re.finditer(r"[.!?](?:\s|$)", cut)]
    if ends and ends[-1] >= max(slot.min_chars, 1):
        return cut[:ends[-1]].strip()
    return text


def _complete_layout_content(slide: dict, spec, research: dict, used_icons: set | None = None,
                             hint: str = "", position: int | None = None) -> None:
    """Lengkapi slot dari headline/subtext tanpa mengarang fakta; buang slot/param yang tidak dikenal layout."""
    headline = str(slide.get("headline") or "").strip()
    subtext = str(slide.get("subtext") or "").strip()
    raw_params = dict(slide.get("params") or {})
    slots = {k: v for k, v in (slide.get("slots") or {}).items() if k in spec.slots}
    used_icons = used_icons if used_icons is not None else set()

    defaults = {"title": headline, "label": headline, "subtitle": subtext, "body": subtext, "context": subtext,
                "statement": headline, "caption": subtext}

    # Layout angka (value atau value_1..N + source): HANYA dari research.facts.stats, tidak pernah dikarang.
    vals = _value_slots(spec)
    if vals and "source" in spec.slots:
        stats = _stats(research)
        if any(not slots.get(v) for v in vals) and len(stats) >= len(vals):
            for i, v in enumerate(vals):
                stat = stats[i]
                slots[v] = str(stat.get("value", ""))
                lab = v.replace("value", "label")
                if lab in spec.slots and not slots.get(lab):
                    slots[lab] = str(stat.get("label") or headline)
            srcs = dict.fromkeys(str(s.get("source", "")) for s in stats[:len(vals)] if s.get("source"))
            slots["source"] = "; ".join(srcs)[:spec.slots["source"].max_chars or 64]
        if len(vals) == 1 and "label" in spec.slots:
            slots.setdefault("label", headline)

    # Layout kutipan: HANYA dari research.facts.quotes (tidak pernah mengarang testimoni).
    if "quote" in spec.slots and not slots.get("quote"):
        quotes = _quotes(research)
        if quotes:
            q = quotes[0]
            slots["quote"] = str(q.get("text", "")).strip()
            for key in ("name", "source"):
                if key in spec.slots and q.get(key):
                    slots[key] = str(q[key]).strip()

    # Nomor langkah: urutan slide isi (boleh ditimpa LLM lewat slots.number).
    if "number" in spec.slots and not slots.get("number") and position is not None:
        slots["number"] = f"{position + 1:02d}"

    # Layout dua sisi: item hanya dari yang eksplisit diberikan LLM (slots atau params).
    for side in ("left", "right"):
        name = f"{side}_items"
        if name in spec.slots and not slots.get(name):
            explicit = raw_params.get(name) or ([str(raw_params[f"{side}_text"])] if raw_params.get(f"{side}_text") else [])
            if explicit:
                slots[name] = list(explicit)
        label = f"{side}_label"
        if label in spec.slots and not slots.get(label):
            slots[label] = str(raw_params.get(f"{side}_title") or ("Sebelum" if side == "left" else "Sesudah"))

    # Layout CTA kata kunci komentar: keyword = satu kata topik, verb konsisten dengan komentar.
    if "keyword" in spec.slots:
        kw = re.sub(r"\s+", "", str(slots.get("keyword") or "")).upper()
        if not (re.fullmatch(r"[A-Z0-9]{2,12}", kw) and kw.lower() not in _ACTION_WORDS):
            kw = _keyword_from(hint, headline, subtext)
        slots["keyword"] = kw[:spec.slots["keyword"].max_chars or 12]
        if "verb" in spec.slots:
            verb = str(slots.get("verb") or "").strip().lower()
            slots["verb"] = verb if verb in _CTA_VERBS else "komen"

    for name, slot in spec.slots.items():
        value = slots.get(name)
        if slot.type == "icon":
            slots[name] = _pick_icon(f"{headline} {subtext}", value, used_icons)
            used_icons.add(slots[name])
            continue
        if slot.type == "list":
            if not value and name not in ("left_items", "right_items"):
                value = list(raw_params.get("items") or [])
                if len(value) < slot.min_items:
                    value = [p.strip() for p in re.split(r"[.!?;]\s*", subtext) if p.strip()]
            if isinstance(value, list) and slot.max_items:
                value = value[:slot.max_items]
            slots[name] = value or []
            continue
        generic = name in defaults     # hanya slot generik boleh diisi dari headline/subtext
        if not value and generic:
            value = defaults[name]
        value = _fit_text(value, slot) if value else ""
        if generic and slot.required and len(value) < slot.min_chars:
            alt = headline if len(headline) >= slot.min_chars else subtext
            if len(alt) >= slot.min_chars:
                value = _fit_text(alt, slot)
        slots[name] = value        # slot spesifik (myth, fact, before, quote, name, ...) dibiarkan kosong bila LLM tak mengisi

    slide["slots"] = {k: v for k, v in slots.items() if v not in (None, "", [])}
    slide["params"] = {n: str(raw_params[n]) for n, p in spec.params.items()
                       if n in raw_params and str(raw_params[n]) in p.enum}


def _clean_emphasis(slide: dict, spec=None, freq: Counter | None = None) -> None:
    """Aksen hemat: frasa harus ada di slot beraksen, maks MAX_EMPHASIS frasa (tiap frasa maks 3 kata),
    dan bukan seluruh judul. Bila tidak ada yang layak, kode memilih SATU kata kunci dari judul."""
    raw = slide.get("emphasis") or []
    raw = [raw] if isinstance(raw, str) else list(raw)
    headline, subtext = str(slide.get("headline") or ""), str(slide.get("subtext") or "")
    slots = slide.get("slots") or {}
    names = [n for n in slots if spec is None or (n in spec.slots and spec.slots[n].emphasis)] or list(slots)
    blob = " ".join(_text_of(slots[n]) for n in names if slots.get(n)).lower()
    out: list[str] = []
    for item in raw:
        item = str(item).strip()
        if item in {"headline", "subtext"}:
            continue            # shorthand LLM, bukan frasa: pemilih kata kunci di bawah yang memutuskan
        if not item or _words(item) > 3 or item.lower() not in blob or item in out:
            continue
        if _words(headline) >= 3 and item.lower() in headline.lower() and len(item) >= WHOLE_TEXT_RATIO * len(headline):
            continue            # seluruh judul di-blok = bukan penekanan (renderer juga mengabaikannya)
        out.append(item)
    if not out and spec is not None and slide.get("role") != "cta":
        words = [re.sub(r"[^\w\-%]", "", w) for w in headline.split()]
        cands = [w for w in words if len(w) >= 5 and w.lower() not in _STOPWORDS and w.lower() in blob]
        if cands and _words(headline) >= 3:
            freq = freq or Counter()   # kata topik (paling sering muncul di carousel) diutamakan, lalu yang terpanjang
            out.append(max(cands, key=lambda w: (freq[w.lower()], len(w), -words.index(w))))
    slide["emphasis"] = out[:MAX_EMPHASIS]


# ---------------------------------------------------------------- pemilihan layout (komposisi)

class _Ctx:
    """Keadaan berjalan saat menyusun carousel dari kiri ke kanan."""

    def __init__(self, approved, avail, research, history, rng, hint=""):
        self.approved, self.avail, self.research, self.hint = approved, list(avail), research, hint
        self.usage = _usage(history)
        self.blocked_covers = _recent_covers(history, approved)
        self.past_content = [h.get("content") or [] for h in (history or [])[:2]]
        self.past_cta = {c for h in (history or [])[:1] for c in (h.get("cta") or []) if c}   # CTA post terakhir
        self.cpos: int | None = None    # indeks slide isi yang sedang dipilih (None untuk cover/cta)
        self.slide: dict | None = None  # slide yang sedang dipilih layout-nya (untuk skor CTA)
        self.rng = rng
        self.prev = None            # spec slide sebelumnya
        self.prev_photo = False
        self.used: list[str] = []
        self.photo = 0
        self.poses: list[str] = []
        self.icons: set = set()


def _adapted(slide: dict, spec, ctx: _Ctx):
    """Salinan slide yang diisi untuk `spec`; (layak, salinan). Layak = lolos validasi slot."""
    trial = {k: slide.get(k) for k in ("role", "headline", "subtext", "emphasis")}
    old_slots = dict(slide.get("slots") or {})
    same = slide.get("layout_id") == spec.id
    slots = dict(old_slots) if same else {k: deepcopy(v) for k, v in old_slots.items()
                                          if k in spec.slots and spec.slots[k].type == _slot_type(slide, k, ctx)}
    if not same:   # daftar poin dari layout lama boleh dipakai ulang oleh layout berlist
        lists = [v for v in old_slots.values() if isinstance(v, list) and v]
        for name, s in spec.slots.items():
            if s.type == "list" and not slots.get(name) and name not in ("left_items", "right_items") and lists:
                slots[name] = deepcopy(lists[0])
    trial["slots"] = slots
    trial["params"] = dict(slide.get("params") or {})
    _complete_layout_content(trial, spec, ctx.research, set(ctx.icons), ctx.hint, ctx.cpos)
    issues = validate_content(spec, trial["slots"], trial["params"], [])
    return (not issues), trial


def _slot_type(slide: dict, name: str, ctx: _Ctx) -> str | None:
    old = ctx.approved.get(slide.get("layout_id"))
    return old.slots[name].type if old and name in old.slots else None


def _score(spec, ctx: _Ctx) -> float:
    s = 2.0 * ctx.usage.get(spec.id, 0.0)
    if spec.id in ctx.used:
        s += 5.0
    if _repeats_position(spec, ctx):
        s += 3.0
    if ctx.slide is not None and spec.meta.role == "cta" and _layout_actions(spec) & _cta_intents(ctx.slide):
        s -= 2.0                   # aksi yang diminta teks persis dilayani layout ini
    prev = ctx.prev
    if prev is not None:
        s += 1.5 * len(set(spec.meta.tags) & set(prev.meta.tags))
        if spec.meta.density == prev.meta.density:
            s += 1.0
        if ctx.prev_photo and spec.meta.needs_photo != "none":
            s += 1.5
    if spec.meta.needs_photo != "none":
        if ctx.photo >= MAX_PHOTO_SLIDES:
            s += 4.0
        elif ctx.photo < MIN_PHOTO_SLIDES:
            s -= 1.0
    return s + ctx.rng.random() * 0.6


_CTA_INTENT = {"save": ("simpan", "save", "bookmark"),
               "share": ("bagikan", "share", "teruskan", "kirim ke"),
               "comment": ("komen", "comment", "jawab", "balas", "ceritakan"),
               "follow": ("ikuti", "follow")}
_CTA_TAGS = {"save": "save", "share": "share", "comment": "comment", "comment_keyword": "comment",
             "question_comment": "comment", "follow": "follow"}


def _cta_intents(slide: dict) -> set:
    """Aksi yang DIMINTA teks slide (simpan/bagikan/komen/ikuti), dibaca dari headline + subtext."""
    text = f"{slide.get('headline', '')} {slide.get('subtext', '')}".lower()
    return {k for k, words in _CTA_INTENT.items() if any(w in text for w in words)}


def _layout_actions(spec) -> set:
    """Aksi yang DIKLAIM layout lewat tag cta:* atau slot keyword. Kosong = layout generik (tidak mengklaim aksi)."""
    acts = {_CTA_TAGS[tag[4:]] for tag in spec.meta.tags if tag.startswith("cta:") and tag[4:] in _CTA_TAGS}
    if "keyword" in spec.slots:
        acts.add("comment")
    return acts


def _cta_misaligned(spec, slide: dict) -> bool:
    """CTA yang mengklaim aksi berbeda dari yang diminta teks (mis. layout 'Simpan/Bagikan' untuk ajakan komentar)."""
    if slide.get("role") not in {"cta", "single"} or spec.meta.role != "cta":
        return False
    acts, wanted = _layout_actions(spec), _cta_intents(slide)
    return bool(acts and wanted and not (acts & wanted))


def _repeats_position(spec, ctx: _Ctx) -> bool:
    """True bila layout ini menempati posisi isi yang sama dengan salah satu dari 2 post terakhir."""
    if ctx.cpos is None:
        return False
    return any(ctx.cpos < len(seq) and seq[ctx.cpos] == spec.id for seq in ctx.past_content)


def _hard_ok(spec, role: str, ctx: _Ctx) -> bool:
    if ctx.prev is not None and spec.id == ctx.prev.id:
        return False
    if role in {"cover", "single"} and spec.id in ctx.blocked_covers:
        return False
    if spec.meta.needs_photo == "required" and (not ctx.avail or ctx.photo >= MAX_PHOTO_SLIDES):
        return False
    return True


def _select(slide: dict, ctx: _Ctx):
    """Pilih layout final. LLM dihormati bila memenuhi aturan keras; kalau tidak, kode memilih
    kandidat terbaik berdasarkan skor variasi. Mengembalikan (spec, salinan_terisi) atau (None, None)."""
    role = slide.get("role")
    ctx.slide = slide
    allowed = SLIDE_TO_LAYOUT_ROLES.get(role, CONTENT_ROLES)
    cands = []
    for spec in ctx.approved.values():
        if spec.meta.role in allowed:
            ok, trial = _adapted(slide, spec, ctx)
            if ok:
                cands.append((spec, trial))
    pool = [c for c in cands if _hard_ok(c[0], role, ctx)]
    current = ctx.approved.get(slide.get("layout_id"))
    keep = next((c for c in pool if c[0] is current), None)
    fresh = [c for c in pool if c[0].id not in ctx.used] or pool
    def misaligned(c) -> bool:
        return _cta_misaligned(c[0], slide)

    def repeated(c) -> bool:
        return _repeats_position(c[0], ctx) or (role == "cta" and c[0].id in ctx.past_cta)

    # Urutan prioritas: selaras & baru > selaras tapi berulang > (terakhir) apa pun yang tersisa.
    aligned = [c for c in fresh if not misaligned(c)]
    novel = [c for c in aligned if not repeated(c)]
    if keep and keep[0].id not in ctx.used and not misaligned(keep) and (not repeated(keep) or not novel):
        return keep
    if fresh:
        return min(novel or aligned or fresh, key=lambda c: _score(c[0], ctx))
    if keep:
        return keep
    if cands:                      # semua kandidat melanggar aturan keras: ambil terbaik, validator yang menilai
        return min(cands, key=lambda c: _score(c[0], ctx))
    return None, None


def _assign_pose(slide: dict, spec, ctx: _Ctx, want_photo_hint: bool) -> bool:
    """Tegakkan pose sesuai kemampuan layout, kuota foto, dan variasi pose. True bila slide berfoto."""
    if spec.meta.needs_photo == "none" or not ctx.avail:
        slide["pose_tags"] = []
        return False
    allowed = [p for p in ctx.avail if not spec.meta.pose_tags or p in spec.meta.pose_tags] or list(ctx.avail)
    given = [p for p in (slide.get("pose_tags") or []) if p in allowed]
    required = spec.meta.needs_photo == "required"
    if not required and (ctx.photo >= MAX_PHOTO_SLIDES or not (given or want_photo_hint)):
        slide["pose_tags"] = []
        return False
    last = ctx.poses[-1] if ctx.poses else None
    if given and not (last in given and len(allowed) > 1 and given == [last]):
        slide["pose_tags"] = given[:2]
    else:
        counts = Counter(ctx.poses)
        options = [p for p in allowed if p != last] or allowed
        best = min(counts[p] for p in options)
        slide["pose_tags"] = [ctx.rng.choice([p for p in options if counts[p] == best])]
    ctx.poses.append(slide["pose_tags"][0])
    return True


def _compose(slides: list[dict], approved: dict, avail, research: dict, history: list[dict], seed: int,
             hint: str = "") -> None:
    """Susun ulang layout/pose/ikon semua slide secara deterministik (seed) dengan memori antar post."""
    ctx = _Ctx(approved, avail, research, history, random.Random(seed), hint)
    total = len(slides)
    specs: list = [None] * total
    content_seen = 0
    for i, slide in enumerate(slides):
        ctx.cpos = None
        if slide.get("role") == "content":
            ctx.cpos, content_seen = content_seen, content_seen + 1
        spec, trial = _select(slide, ctx)
        if spec is None:           # tidak ada layout layak sama sekali: biarkan, validator melaporkan
            ctx.prev, ctx.prev_photo = None, False
            continue
        slide["layout_id"] = spec.id
        slide["slots"], slide["params"] = trial["slots"], trial["params"]
        remaining = total - i - 1
        hint = ctx.photo < MIN_PHOTO_SLIDES and slide.get("role") == "content" and remaining <= 1
        photo = _assign_pose(slide, spec, ctx, want_photo_hint=hint)
        ctx.photo += int(photo)
        ctx.prev_photo = photo
        ctx.prev = spec
        ctx.used.append(spec.id)
        specs[i] = spec
        ctx.icons.update(v for n, v in slide["slots"].items()
                         if n in spec.slots and spec.slots[n].type == "icon")
    if ctx.photo < MIN_PHOTO_SLIDES and ctx.avail:
        _ensure_photo(slides, specs, ctx)


def _ensure_photo(slides: list[dict], specs: list, ctx: _Ctx) -> None:
    """Pastikan minimal MIN_PHOTO_SLIDES slide berfoto: aktifkan foto opsional, atau tukar layout isi."""
    content_idx = [i for i, s in enumerate(slides) if s.get("role") == "content" and specs[i] is not None]
    for i in content_idx:
        if specs[i].meta.needs_photo == "optional":
            if _assign_pose(slides[i], specs[i], ctx, want_photo_hint=True):
                ctx.photo += 1
                return
    for i in ctx.rng.sample(content_idx, len(content_idx)):
        neighbours = {specs[j].id for j in (i - 1, i + 1) if 0 <= j < len(specs) and specs[j] is not None}
        options = [s for s in ctx.approved.values()
                   if s.meta.role in CONTENT_ROLES and s.meta.needs_photo != "none" and s.id not in neighbours]
        trials = [(s, t) for s in options for ok, t in [_adapted(slides[i], s, ctx)] if ok]
        if trials:
            spec, trial = min(trials, key=lambda c: ctx.usage.get(c[0].id, 0.0))
            slides[i]["layout_id"], slides[i]["slots"], slides[i]["params"] = spec.id, trial["slots"], trial["params"]
            specs[i] = spec
            if _assign_pose(slides[i], spec, ctx, want_photo_hint=True):
                ctx.photo += 1
            return


# ---------------------------------------------------------------- style pack

def _hash_int(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _pick_style(base_seed: int, brand: dict, history: list[dict], total: int) -> dict:
    """Seed deterministik, digeser (salt) agar pola/permukaan tidak sama dengan post terakhir."""
    try:
        from src.layouts.style.packs import build_pack
        recent = [h.get("style") or {} for h in (history or [])]
        patterns = {s.get("pattern") for s in recent[:2] if s.get("pattern")}
        pack_ids = {s.get("pack_id") for s in recent if s.get("pack_id")}
        want_light = len(recent) >= 2 and all(s.get("surface") == "dark" for s in recent[:2])
        fallback = None
        for salt in range(24):
            seed = base_seed if salt == 0 else _hash_int(f"{base_seed}:{salt}")
            pack = build_pack(seed, brand, total)
            if pack["pattern"] in patterns or pack["pack_id"] in pack_ids:
                continue
            info = {"seed": seed, "pack_id": pack["pack_id"], "pattern": pack["pattern"], "surface": pack["surface"]}
            if not want_light or pack["surface"] == "light":
                return info
            fallback = fallback or info
        if fallback:
            return fallback
        pack = build_pack(base_seed, brand, total)
        return {"seed": base_seed, "pack_id": pack["pack_id"], "pattern": pack["pattern"], "surface": pack["surface"]}
    except Exception:
        return {"seed": base_seed}


# ---------------------------------------------------------------- normalisasi (mekanis, di kode)

def normalize(plan: dict, brand: dict, research: dict, *, history: list[dict] | None = None,
              approved: dict | None = None) -> dict:
    """Rapikan & tegakkan hal-hal mekanis di kode (bukan tugas model)."""
    approved = approved if approved is not None else _approved()
    history = history or []
    avail = list(brand.get("available_poses", []))
    slides = [s for s in (plan.get("slides") or []) if isinstance(s, dict)]
    plan["slides"] = slides

    unknown = []
    for s in slides:
        tags = s.get("pose_tags") or []
        unknown += [t for t in tags if t not in avail]
        s["pose_tags"] = [t for t in tags if t in avail]
    if plan.get("format") == "single_image" and slides:
        slides[0]["role"] = "single"

    base_seed = _hash_int(f"{plan.get('concept', '')}\0{plan.get('content_pillar', '')}")
    style = _pick_style(base_seed, brand, history, max(1, len(slides)))
    hint = str(slides[0].get("headline") or plan.get("concept") or "") if slides else ""
    _compose(slides, approved, avail, research, history, style["seed"], hint)
    freq: Counter = Counter()
    for text in [plan.get("concept", "")] + [f"{s.get('headline', '')} {s.get('subtext', '')}" for s in slides]:
        freq.update(set(tok for tok in _tokens(str(text)) if len(tok) >= 4 and tok not in _STOPWORDS))
    for s in slides:
        _clean_emphasis(s, approved.get(s.get("layout_id")), freq)
    plan["style"] = style
    if unknown and not plan.get("new_pose_request"):
        plan["new_pose_request"] = ", ".join(dict.fromkeys(unknown))

    tags = []
    for h in plan.get("hashtags", []) or []:
        h = "#" + str(h).strip().lstrip("#").replace(" ", "")
        if len(h) > 1 and h.lower() not in [t.lower() for t in tags]:
            tags.append(h)
    plan["hashtags"] = tags[:8]

    # jadwal: KODE yang menentukan mana slot dari riset dan mana asumsi
    sched = plan.get("schedule") or {}
    pt = _nt(json.dumps(research.get("posting_time", {}), ensure_ascii=False))
    out = []
    for sl in sched.get("slots", []) or []:
        t = (sl.get("time") if isinstance(sl, dict) else str(sl)) or ""
        t = t.replace(" [asumsi, bukan dari riset]", "").strip()
        if not t:
            continue
        from_research = bool(_nt(t)) and _nt(t) in pt
        out.append({"time": t if from_research else f"{t} [asumsi, bukan dari riset]",
                    "source": "riset" if from_research else "asumsi"})
    sched["slots"] = out
    sched["suggested_time"] = " | ".join(s["time"] for s in out)
    sched["is_hypothesis"] = True
    sched["timezone_note"] = TZ_NOTE
    plan["schedule"] = sched
    return plan


# ---------------------------------------------------------------- validasi

def _unsupported_numbers(text: str, blob: str, topic: str = "") -> list[str]:
    nums = re.findall(r"(\d+(?:[.,]\d+)?)\s?%", text) + re.findall(r"\b(\d{2,})\b", text)
    combined_blob = blob + topic
    return [n for n in dict.fromkeys(nums) if n not in combined_blob]


def _research_urls(research: dict) -> set[str]:
    """Semua URL yang benar-benar ada di hasil riset (sources, source_url, source_urls, facts, dst).

    Model sering mengutip URL dari posting_time.source_urls / trending_formats[].source_url
    yang tidak ikut masuk ke daftar `sources` tingkat atas; itu tetap URL asli, bukan karangan.
    """
    found: set[str] = set()

    def walk(node):
        if isinstance(node, str):
            for m in re.findall(r"https?://[^\s\"'<>)\]]+", node):
                found.add(m.rstrip(".,;/"))
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)

    walk(research)
    return found


def validate(plan: dict, blob: str, research: dict, topic: str = "", *, history: list[dict] | None = None,
             approved: dict | None = None) -> list[str]:
    issues = []
    approved = approved if approved is not None else _approved()
    stats = _stats(research)
    fmt = plan.get("format")
    slides = [s for s in (plan.get("slides") or []) if isinstance(s, dict)]
    if fmt not in ALLOWED_FORMATS:
        issues.append(f"format harus single_image atau carousel (bukan {fmt!r})")
    elif fmt == "single_image" and len(slides) != 1:
        issues.append("single_image harus tepat 1 slide")
    elif fmt == "carousel":
        if not MIN_CAROUSEL_SLIDES <= len(slides) <= MAX_CAROUSEL_SLIDES:
            issues.append(f"carousel harus {MIN_CAROUSEL_SLIDES}-{MAX_CAROUSEL_SLIDES} slide: cover, 3-4 content, CTA")
        elif slides[0].get("role") != "cover" or slides[-1].get("role") != "cta":
            issues.append('carousel: slide pertama harus role "cover" dan slide terakhir role "cta"')
        elif not 3 <= sum(s.get("role") == "content" for s in slides[1:-1]) <= 4:
            issues.append('carousel harus punya 3-4 slide role "content" di antara cover dan CTA')

    blocked = _recent_covers(history or [], approved)
    for i, s in enumerate(slides, 1):
        if not s.get("headline"):
            issues.append(f"slide {i}: headline kosong")
        if _words(s.get("headline")) > 8:
            issues.append(f"slide {i}: headline lebih dari 8 kata")
        if _words(s.get("subtext")) > 22:
            issues.append(f"slide {i}: subtext lebih dari 22 kata")
        if fmt == "carousel" and s.get("role") == "content" and _words(s.get("subtext")) < 5:
            issues.append(f"slide {i}: subtext content terlalu pendek; isi dengan penjelasan/aksi spesifik (minimal 5 kata)")
        spec = approved.get(s.get("layout_id"))
        if spec is None:
            issues.append(f"slide {i}: layout_id '{s.get('layout_id')}' tidak ada atau belum approved")
            continue
        if spec.meta.role not in SLIDE_TO_LAYOUT_ROLES.get(s.get("role"), frozenset()):
            issues.append(f"slide {i}: role layout '{spec.meta.role}' tidak cocok dengan role slide '{s.get('role')}'")
        issues.extend(f"slide {i}: {m}" for m in validate_content(
            spec, s.get("slots") or {}, s.get("params") or {}, s.get("emphasis") or []))
        if spec.meta.needs_photo == "required" and not s.get("pose_tags"):
            issues.append(f"slide {i}: layout '{spec.id}' membutuhkan foto/pose")
        if s.get("role") in {"cover", "single"} and spec.id in blocked:
            issues.append(f"slide {i}: layout cover '{spec.id}' masih cooldown dari post terakhir")
        slots = s.get("slots") or {}
        vals = _value_slots(spec)
        if vals and "source" in spec.slots:
            if not stats:
                issues.append(f"slide {i}: layout '{spec.id}' butuh statistik bersumber dari research.facts.stats")
            else:
                known = {str(st.get("value", "")) for st in stats}
                wrong = [v for v in vals if str(slots.get(v, "")) not in known]
                if wrong:
                    issues.append(f"slide {i}: {', '.join(wrong)} harus sama persis dengan nilai di research.facts.stats")
        if "quote" in spec.slots:
            known_q = {_norm_text(q.get("text")) for q in _quotes(research)}
            if not known_q:
                issues.append(f"slide {i}: layout '{spec.id}' butuh kutipan bersumber dari research.facts.quotes (jangan mengarang)")
            elif _norm_text(slots.get("quote")) not in known_q:
                issues.append(f"slide {i}: kutipan harus sama persis dengan salah satu research.facts.quotes")

    if fmt == "carousel" and len(slides) >= MIN_CAROUSEL_SLIDES:
        issues.extend(validate_rhythm(slides))

    cap = plan.get("caption") or ""
    if not cap or len(cap) > 2200:
        issues.append("caption kosong atau lebih dari 2200 karakter")
    if not 3 <= len(plan.get("hashtags", [])) <= 8:
        issues.append("hashtag harus 3-8")
    sched = plan.get("schedule") or {}
    if not sched.get("slots"):
        issues.append("schedule.slots kosong")
    if not sched.get("ab_test"):
        issues.append("schedule.ab_test kosong")

    valid_urls = _research_urls(research)
    fake = [u for u in plan.get("research_used", []) if str(u).rstrip(".,;/") not in valid_urls]
    if fake:
        issues.append(f"research_used berisi URL yang tidak ada di sources riset: {fake}")

    text = " ".join([cap] + [f"{s.get('headline', '')} {s.get('subtext', '')}" for s in slides])
    bad = _unsupported_numbers(text, blob, topic)
    if bad:
        issues.append(f"angka tanpa sumber di teks: {bad}. Hapus atau tulis tanpa angka itu")
    low, topic_low = text.lower(), (topic or "").lower()
    hits = [m.group(0) for p in CLAIM_PATTERNS for m in [re.search(p, low)] if m]
    actual_hits = [h for h in hits if h not in topic_low]
    if actual_hits:
        issues.append(f"mengandung janji hasil/klaim kesehatan: {actual_hits}. Tulis ulang sebagai saran praktis tanpa janji")
    return issues


# ---------------------------------------------------------------- orkestrasi

def run(topic: str, research: dict, brand: dict, client=None, on_step=print, *, ctx=None,
        history: list[dict] | None = None) -> dict:
    if ctx is not None and getattr(ctx, "llm", None) is not None:
        client = ctx.llm            # token & biaya planner ikut tercatat di run
    elif client is None:
        from src.core.llm import LLMClient
        client = LLMClient()
    model = config.opt("GROQ_MODEL", "openai/gpt-oss-120b")
    approved = _approved()          # dibaca sekali per run, bukan tiap fungsi
    if history is None:
        history = load_history(getattr(ctx, "session", None), exclude_run=getattr(ctx, "run_id", None))
    blob = (json.dumps(research, ensure_ascii=False) + json.dumps(brand, ensure_ascii=False) + topic).replace(" ", "")
    brand_view = {k: brand[k] for k in ("company", "industry", "description", "audience", "tone",
                                        "content_pillars", "rules", "available_poses") if k in brand}
    static = dict(brand=json.dumps(brand_view, ensure_ascii=False, separators=(",", ":")), topic=topic,
                  research=json.dumps(research, ensure_ascii=False, separators=(",", ":")),
                  layout_catalog=_layout_catalog_prompt(approved), variety=_variety_note(history, approved))
    issues, best = [], None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        on_step(f"[planner] percobaan {attempt}" + (f" (memperbaiki {len(issues)} masalah)" if issues else ""))
        fb = ("\nPERBAIKI masalah dari percobaan sebelumnya:\n- " + "\n- ".join(issues)) if issues else ""
        resp = client.chat(
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": PROMPT.format(issues=fb, **static)}],
            step="planner", model=model, temperature=RETRY_TEMPERATURES[min(attempt, len(RETRY_TEMPERATURES)) - 1],
            max_completion_tokens=4096)
        plan = _json_object(resp.choices[0].message.content or "")
        if plan is None:
            issues = ["output bukan JSON valid"]
            continue
        plan = normalize(plan, brand, research, history=history, approved=approved)
        issues = validate(plan, blob, research, topic, history=history, approved=approved)
        if best is None or len(issues) <= len(best[1]):
            best = (plan, issues)       # simpan percobaan terbaik, bukan sekadar yang terakhir
        if not issues:
            break
    plan, issues = best if best else (None, issues)
    return {"ok": plan is not None and not issues, "plan": plan, "issues": issues}