"""Rakit HTML satu slide: style pack + layout + chrome (layer stack)."""
from __future__ import annotations

import re
from functools import lru_cache
from html import escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from src.carousel.layouts import registry
from src.carousel.layouts.models import LayoutError, LayoutSpec, validate_content
from src.carousel.layouts.primitives.icons import icon_svg, mark_svg
from src.carousel.layouts.style import packs

ROOT = Path(__file__).resolve().parents[2]
RENDER_DIR = Path(__file__).resolve().parent
FONT_DIR = RENDER_DIR / "fonts"
LAYOUTS_DIR = registry.LAYOUTS_DIR


# ---------- helper teks (dipakai template lewat global/filter) ----------

MAX_EMPHASIS_PHRASES = 2     # aksen hemat: hanya 2 frasa pertama yang dipakai
WHOLE_TEXT_RATIO = 0.7       # frasa yang menutupi >=70% teks (>=3 kata) bukan penekanan, abaikan


def _emphasis_ranges(text: str, emphasis: list[str]) -> list[tuple[int, int]]:
    ranges = []
    many_words = len(str(text).split()) >= 3
    for e in [x for x in (emphasis or []) if x][:MAX_EMPHASIS_PHRASES]:
        # Cocokkan kata utuh: batas \w hanya dipakai di sisi yang berupa huruf/angka (mis. "%" tetap bisa)
        pattern = (r"(?<!\w)" if e[0].isalnum() or e[0] == "_" else "") + re.escape(e) + \
                  (r"(?!\w)" if e[-1].isalnum() or e[-1] == "_" else "")
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            if many_words and (m.end() - m.start()) >= WHOLE_TEXT_RATIO * len(text):
                continue   # seluruh judul di-blok = tidak ada penekanan sama sekali
            ranges.append((m.start(), m.end()))
            break          # aksen hemat: hanya kemunculan PERTAMA tiap frasa yang ditandai
    return ranges


def emph_html(text: str, emphasis: list[str] | None = None) -> Markup:
    """Escape teks lalu bungkus bagian emphasis dengan <em class="hl">."""
    text = str(text)
    ranges = sorted(_emphasis_ranges(text, emphasis or []))
    out, pos = [], 0
    for s, e in ranges:
        if s < pos:
            continue
        out.append(escape(text[pos:s]))
        out.append(f'<em class="hl">{escape(text[s:e])}</em>')
        pos = e
    out.append(escape(text[pos:]))
    return Markup("".join(out))


def balance_lines(words: list[str], n: int) -> list[list[int]]:
    """Bagi indeks kata menjadi <=n baris dengan panjang karakter paling seimbang (DP)."""
    n = max(1, min(n, len(words)))
    lens = [len(w) for w in words]
    total = sum(lens) + len(words) - 1
    ideal = total / n
    m = len(words)
    prefix = [0]
    for ln in lens:
        prefix.append(prefix[-1] + ln)

    def seg(i: int, j: int) -> int:  # panjang kata i..j-1 termasuk spasi
        return prefix[j] - prefix[i] + (j - i - 1)

    INF = float("inf")
    best = [[INF] * (m + 1) for _ in range(n + 1)]
    cut = [[0] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for k in range(1, n + 1):
        for j in range(k, m + 1):
            for i in range(k - 1, j):
                cost = best[k - 1][i] + (seg(i, j) - ideal) ** 2
                if cost < best[k][j]:
                    best[k][j], cut[k][j] = cost, i
    groups, j = [], m
    for k in range(n, 0, -1):
        i = cut[k][j]
        groups.append(list(range(i, j)))
        j = i
    return groups[::-1]


def title_lines(text: str, n: int, emphasis: list[str] | None = None) -> list[Markup]:
    """Pecah judul jadi n baris seimbang; kata beremphasis berurutan dibungkus satu <em class=hl>."""
    text = str(text).strip()
    words = text.split()
    if not words:
        return []
    ranges = _emphasis_ranges(text, emphasis or [])
    spans, cursor = [], 0
    for w in words:
        start = text.index(w, cursor)
        spans.append((start, start + len(w)))
        cursor = start + len(w)
    marked = [any(s < r_end and e > r_start for r_start, r_end in ranges) for s, e in spans]
    lines = []
    for idxs in balance_lines(words, int(n)):
        parts, run = [], []
        for i in idxs:        # kata beremphasis yang berurutan digabung jadi SATU kotak (tanpa celah antar kata)
            if marked[i]:
                run.append(words[i])
                continue
            if run:
                parts.append(f'<em class="hl">{escape(" ".join(run))}</em>')
                run = []
            parts.append(str(escape(words[i])))
        if run:
            parts.append(f'<em class="hl">{escape(" ".join(run))}</em>')
        lines.append(Markup(" ".join(parts)))
    return lines


def _clean_word(text: str, which: str) -> str:
    words = [re.sub(r"[^\w\-]", "", w) for w in str(text).split()]
    words = [w for w in words if w]
    if not words:
        return ""
    return (words[0] if which == "first" else words[-1]).upper()


# ---------- font, chrome, environment ----------

def fonts_css(brand: dict) -> str:
    fonts = brand.get("fonts") or {}
    names = {"display": "--f-display", "body": "--f-body", "medium": "--f-medium"}
    fallback_files = {"display": "Poppins-Bold.ttf", "body": "Poppins-Regular.ttf",
                      "medium": "Poppins-Medium.ttf"}
    faces, root = [], []
    for key, var in names.items():
        spec = fonts.get(key) or {"file": fallback_files[key], "weight": 700 if key == "display" else 500 if key == "medium" else 400}
        candidate = Path(spec["file"])
        path = candidate if candidate.is_absolute() else FONT_DIR / candidate.name
        if not path.exists():
            raise LayoutError(f"file font tidak ada: {path}")
        fam = f"B-{key}"
        faces.append(f"@font-face{{font-family:'{fam}';src:url('{path.as_uri()}');font-weight:{spec.get('weight', 400)};font-style:normal}}")
        root.append(f"{var}:'{fam}'")
    return "".join(faces) + ":root{" + ";".join(root) + "}"


def chrome_html(brand: dict, index: int, total: int) -> Markup:
    c = brand.get("chrome") or {}
    parts = []
    if c.get("header", True):
        logo = brand.get("logo_path")
        logo_file = (ROOT / logo) if logo else None
        if logo_file and logo_file.exists():
            mark = f'<img src="{logo_file.as_uri()}" alt="">'
        else:
            mark = f'<i class="sq"></i>{escape(c.get("brand_text") or brand.get("company", ""))}'
        counter = ""
        if c.get("page_counter", True) and total > 1:
            counter = (f'<div class="pagectr" data-q="pager" data-kind="chrome" data-min-font="22">'
                       f'{index + 1}/{total}</div>')
        parts.append(f'<div class="chrome-h"><div class="brandmark" data-q="brand" data-kind="chrome" '
                     f'data-min-font="22">{mark}</div>{counter}</div>')
    foot = c.get("footer") or {}
    if foot.get("show", True):
        lines = "".join(f"<span>{escape(x)}</span>" for x in foot.get("lines", []))
        swipe = ""
        if c.get("swipe_hint", True) and index < total - 1:
            swipe = '<div class="swipe" data-q="swipe" data-kind="chrome" data-min-font="22">swipe &rsaquo;</div>'
        parts.append(f'<div class="chrome-f"><div class="foot-lines" data-q="contact" data-kind="chrome" '
                     f'data-min-font="22">{lines}</div>{swipe}</div>')
    return Markup("".join(parts))


@lru_cache(maxsize=1)
def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(LAYOUTS_DIR)), autoescape=select_autoescape(["html"]),
                      undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.filters["emph"] = emph_html
    env.globals.update(title_lines=title_lines, icon_svg=icon_svg, mark_svg=mark_svg, first_word=lambda t: _clean_word(t, "first"),
                       last_word=lambda t: _clean_word(t, "last"))
    return env


@lru_cache(maxsize=None)
def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


# ---------- API utama ----------

def render_layout_html(spec: LayoutSpec, slots: dict, params: dict | None, emphasis: list[str] | None,
                       pack: dict, index: int, total: int, brand: dict,
                       photo_url: str | None = None) -> str:
    if spec.meta.needs_photo == "required" and not photo_url:
        raise LayoutError(f"{spec.id}: layout ini butuh foto (photo_url kosong)")
    params = dict(params or {})
    full_params = {n: p.default for n, p in spec.params.items()}
    full_params.update({k: str(v) for k, v in params.items()})
    errors = validate_content(spec, slots, full_params, emphasis)
    if errors:
        raise LayoutError(f"{spec.id}: konten tidak valid: " + "; ".join(errors))
    ctx = {
        "layout_id": spec.id, "slots": {n: slots.get(n) for n in spec.slots}, "params": full_params, "emphasis": emphasis or [],
        "S": spec.slots, "photo_url": photo_url, "index": index, "total": total,
        "surface": pack["surface"], "emphasis_style": pack["emphasis_style"],
        "css_vars": packs.css_vars(pack), "fonts_css": fonts_css(brand),
        "base_css": _read(str(RENDER_DIR / "base.css")),
        "prim_css": _read(str(LAYOUTS_DIR / "primitives" / "primitives.css")),
        "layout_css": _read(str(spec.path / "layout.css")),
        "autofit_js": _read(str(RENDER_DIR / "autofit.js")),
        "bg": Markup(packs.bg_html(pack, index)), "deco": Markup(packs.deco_html(pack, index)),
        "chrome": chrome_html(brand, index, total),
    }
    return _env().get_template(f"{spec.id}/layout.html").render(**ctx)
