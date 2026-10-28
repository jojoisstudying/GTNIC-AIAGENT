"""Subtitle kinetik, headline, dan kartu CTA brand untuk video vertikal (Pillow + NumPy).

Perbaikan dibanding versi lama:
- Import `Dict`/`Any` hilang -> NameError saat import di Python < 3.14 (anotasi baru ditunda di 3.14).
- Badge highlight kata: posisi vertikal kini memakai metrik font (ascent/descent), bukan bbox per
  kata, sehingga badge tidak bergeser dan tingginya konsisten. Jarak antarkata selalu lebih lebar
  dari padding badge, jadi badge tidak lagi menimpa kata di sebelahnya.
- Semua teks diukur dan dimuat ke dalam safe-area (shrink / wrap / elipsis), tidak ada lagi
  teks selebar 1748 px di kanvas 1080 px.
- Warna, logo, nama, dan kontak kartu CTA diambil dari config/brand.json (bukan hardcode).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

from src import config
from src.reels.models import WordTiming

FONT_PATH_DEFAULT = config.ROOT / "src" / "render" / "fonts" / "Poppins-Bold.ttf"
FONT_PATH_REGULAR = config.ROOT / "src" / "render" / "fonts" / "Poppins-Regular.ttf"
BRAND_JSON_PATH = config.ROOT / "config" / "brand.json"

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

# Safe zone Instagram Reels (9:16)
SAFE_TOP = 250       # hindari ikon header IG
SAFE_BOTTOM = 1550   # hindari caption & judul audio IG
SUBTITLE_Y = 1200    # area fokus subtitle animasi
HEADLINE_Y = 320     # area headline scene
SIDE_MARGIN = 60     # margin kiri/kanan minimum untuk semua teks

RGBA = Tuple[int, int, int, int]

_FALLBACK_TOKENS = {
    "bg": "#0B2A5B",
    "fg": "#FFFFFF",
    "accent": "#FFB400",
}


# --------------------------------------------------------------------------- brand

@lru_cache(maxsize=4)
def _read_brand_json(path_str: str, mtime_ns: int) -> dict:
    try:
        with open(path_str, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def load_brand() -> dict:
    """Isi config/brand.json (di-cache per perubahan file, jadi aman dipanggil per frame)."""
    try:
        return _read_brand_json(str(BRAND_JSON_PATH), BRAND_JSON_PATH.stat().st_mtime_ns)
    except OSError:
        return {}


def load_brand_tokens(brand: Optional[Dict[str, Any]] = None) -> dict:
    """Token warna: default < colors brand < tokens brand."""
    brand = brand if brand is not None else load_brand()
    tokens = dict(_FALLBACK_TOKENS)
    colors = brand.get("colors") or {}
    if colors.get("primary"):
        tokens["bg"] = colors["primary"]
    if colors.get("accent"):
        tokens["accent"] = colors["accent"]
    if colors.get("text_on_primary"):
        tokens["fg"] = colors["text_on_primary"]
    tokens.update({k: v for k, v in (brand.get("tokens") or {}).items() if v})
    return tokens


def hex_to_rgba(hex_color: str, alpha: int = 255) -> RGBA:
    """Ubah '#FFB400' menjadi (255, 180, 0, alpha). Hex tidak valid -> putih."""
    hex_color = str(hex_color).lstrip("#")
    if len(hex_color) == 6:
        try:
            return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16), alpha)
        except ValueError:
            pass
    return (255, 255, 255, alpha)


def _luminance(rgb: Tuple[int, ...]) -> float:
    def lin(c: int) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _contrast(a: Tuple[int, ...], b: Tuple[int, ...]) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _shade(rgba: RGBA, factor: float, alpha: Optional[int] = None) -> RGBA:
    """factor < 1 menggelapkan, > 1 mencerahkan (menuju putih)."""
    r, g, b, a = rgba
    if factor <= 1:
        r, g, b = (int(v * factor) for v in (r, g, b))
    else:
        t = min(factor - 1.0, 1.0)
        r, g, b = (int(v + (255 - v) * t) for v in (r, g, b))
    return (r, g, b, a if alpha is None else alpha)


def get_palette(brand: Optional[Dict[str, Any]] = None) -> Dict[str, RGBA]:
    """Warna siap pakai dari brand. `accent_fg` dihitung otomatis (kontras tertinggi) bila tidak ada."""
    tokens = load_brand_tokens(brand)
    primary = hex_to_rgba(tokens["bg"])
    accent = hex_to_rgba(tokens["accent"])
    fg = hex_to_rgba(tokens.get("fg", "#FFFFFF"))
    if tokens.get("accent_fg"):
        accent_fg = hex_to_rgba(tokens["accent_fg"])
    else:
        dark = _shade(primary, 0.35)
        white = (255, 255, 255, 255)
        accent_fg = white if _contrast(accent, white) >= _contrast(accent, dark) else dark
    return {"primary": primary, "accent": accent, "fg": fg, "accent_fg": accent_fg}


# --------------------------------------------------------------------------- font & teks

@lru_cache(maxsize=64)
def _load_font(path_str: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path_str, size)


def _font_candidates(regular: bool = False) -> List[Path]:
    bundled = config.ROOT / "assets" / "fonts"
    render_fonts = config.ROOT / "src" / "render" / "fonts"
    if regular:
        return [FONT_PATH_REGULAR, bundled / "DejaVuSans.ttf", render_fonts / "DejaVuSans.ttf"]
    return [FONT_PATH_DEFAULT, bundled / "DejaVuSans-Bold.ttf", render_fonts / "DejaVuSans-Bold.ttf"]


def get_font(size: int = 48, font_path: Optional[Path] = None, regular: bool = False):
    """Font TrueType dengan rantai fallback (Poppins -> DejaVu bawaan repo -> default Pillow)."""
    paths = ([Path(font_path)] if font_path else []) + _font_candidates(regular)
    for p in paths:
        if p.exists():
            return _load_font(str(p), int(size))
    try:
        return ImageFont.load_default(int(size))  # Pillow >= 10.1 (FreeType)
    except TypeError:  # pragma: no cover - Pillow lama
        return ImageFont.load_default()


def _tw(font, text: str) -> float:
    return float(font.getlength(text))


def _wrap_lines(font, text: str, max_w: float) -> List[str]:
    lines: List[str] = []
    cur = ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if _tw(font, trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _ellipsize(font, text: str, max_w: float) -> str:
    if _tw(font, text) <= max_w:
        return text
    text = text.rstrip(" .,;:-")
    while text and _tw(font, text + "…") > max_w:
        text = text[:-1].rstrip(" .,;:-")
    return (text + "…") if text else "…"


def _fit_lines(text: str, max_w: float, start: int, min_size: int, max_lines: int,
               regular: bool = False) -> Tuple[Any, List[str]]:
    """Cari ukuran font terbesar (>= min_size) agar teks muat dalam max_lines baris selebar max_w.
    Jika tetap tidak muat, pakai min_size dan potong dengan elipsis."""
    text = " ".join(str(text).split())
    size = start
    while size >= min_size:
        font = get_font(size, regular=regular)
        lines = _wrap_lines(font, text, max_w)
        if len(lines) <= max_lines and all(_tw(font, ln) <= max_w for ln in lines):
            return font, lines
        size -= 2
    font = get_font(min_size, regular=regular)
    lines = _wrap_lines(font, text, max_w)
    if len(lines) > max_lines:
        kept = lines[:max_lines]
        kept[-1] = " ".join(lines[max_lines - 1:])
        lines = kept
    return font, [_ellipsize(font, ln, max_w) for ln in lines[:max_lines]]


def _line_height(font) -> Tuple[int, int, int]:
    asc, desc = font.getmetrics()
    return asc, desc, asc + desc


def _blank(canvas_w: int, canvas_h: int, fill: RGBA = (0, 0, 0, 0)) -> Image.Image:
    return Image.new("RGBA", (canvas_w, canvas_h), fill)


# --------------------------------------------------------------------------- frasa

def group_words_into_phrases(
    words: List[WordTiming], max_words: int = 4
) -> List[Tuple[int, int, List[WordTiming]]]:
    """
    Kelompokkan kata menjadi frasa pendek (2-4 kata per kartu). Timestamp dibuat menyambung
    supaya highlight tidak berkedip. Return list (start_ms, end_ms, [WordTiming]).
    """
    if not words:
        return []

    seamless_words: List[WordTiming] = []
    for i in range(len(words)):
        w = words[i]
        curr_start = w.start_ms
        if i < len(words) - 1:
            curr_end = max(w.end_ms, words[i + 1].start_ms)
        else:
            curr_end = max(w.end_ms, curr_start + 400)
        seamless_words.append(WordTiming(word=w.word, start_ms=curr_start, end_ms=curr_end))

    phrases = []
    current_chunk: List[WordTiming] = []
    for w in seamless_words:
        current_chunk.append(w)
        if len(current_chunk) >= max_words or w.word.endswith((".", "!", "?", ",")):
            phrases.append((current_chunk[0].start_ms, current_chunk[-1].end_ms, list(current_chunk)))
            current_chunk = []
    if current_chunk:
        phrases.append((current_chunk[0].start_ms, current_chunk[-1].end_ms, list(current_chunk)))
    return phrases


# --------------------------------------------------------------------------- subtitle

def layout_subtitle_phrase(words: List[str], canvas_w: int = CANVAS_WIDTH, font_size: int = 54) -> dict:
    """Hitung posisi tiap kata. Dipisah dari render supaya bisa diuji tanpa piksel.

    Aturan: jarak antarkata >= 2 x padding badge + margin, sehingga badge kata aktif tidak pernah
    menyentuh kata tetangga. Font mengecil otomatis bila frasa tidak muat di safe-area.
    """
    pill_pad_x = 28
    max_total = canvas_w - 2 * SIDE_MARGIN - 2 * pill_pad_x
    size = font_size
    while True:
        font = get_font(size)
        pad_x = max(6, round(size * 0.22))
        pad_y = max(4, round(size * 0.11))
        gap = max(round(_tw(font, " ")), 2 * pad_x + max(4, round(size * 0.1)))
        widths = [_tw(font, w) for w in words]
        total = sum(widths) + gap * max(len(words) - 1, 0)
        if total <= max_total or size <= 32:
            break
        size -= 2

    asc, desc, line_h = _line_height(font)
    start_x = (canvas_w - total) / 2
    xs, cur = [], start_x
    for w in widths:
        xs.append(cur)
        cur += w + gap
    return {
        "font": font, "size": size, "xs": xs, "widths": widths, "gap": gap,
        "pad_x": pad_x, "pad_y": pad_y, "asc": asc, "desc": desc, "line_h": line_h,
        "total": total, "start_x": start_x, "pill_pad_x": pill_pad_x,
        "pill_pad_y": 16, "top": SUBTITLE_Y,
    }


def create_kinetic_subtitle_frame(
    phrase_words: List[WordTiming],
    active_word_index: int,
    canvas_w: int = CANVAS_WIDTH,
    canvas_h: int = CANVAS_HEIGHT,
    font_size: int = 54,
) -> np.ndarray:
    """Frame RGBA transparan: kata lain putih, kata yang sedang diucapkan diberi badge aksen."""
    img = _blank(canvas_w, canvas_h)
    draw = ImageDraw.Draw(img)
    pal = get_palette()

    words = [wt.word for wt in phrase_words]
    L = layout_subtitle_phrase(words, canvas_w, font_size)
    font, top = L["font"], L["top"]
    baseline = top + L["asc"]

    pill_box = [
        L["start_x"] - L["pill_pad_x"],
        top - L["pill_pad_y"] - L["pad_y"],
        L["start_x"] + L["total"] + L["pill_pad_x"],
        top + L["line_h"] + L["pill_pad_y"] + L["pad_y"],
    ]
    draw.rounded_rectangle(pill_box, radius=18, fill=_shade(pal["primary"], 0.9, alpha=205))

    for idx, (word, x, w) in enumerate(zip(words, L["xs"], L["widths"])):
        if idx == active_word_index:
            badge = [x - L["pad_x"], top - L["pad_y"], x + w + L["pad_x"], top + L["line_h"] + L["pad_y"]]
            draw.rounded_rectangle(badge, radius=8, fill=pal["accent"])
            color = pal["accent_fg"]
        else:
            color = pal["fg"]
        draw.text((x, baseline), word, font=font, fill=color, anchor="ls")

    return np.array(img)


# --------------------------------------------------------------------------- headline

def create_headline_overlay_frame(
    headline: str,
    canvas_w: int = CANVAS_WIDTH,
    canvas_h: int = CANVAS_HEIGHT,
    font_size: int = 64,
) -> np.ndarray:
    """Kartu headline di safe-area atas. Mengecil / dua baris bila terlalu panjang."""
    img = _blank(canvas_w, canvas_h)
    if not headline or not headline.strip():
        return np.array(img)

    draw = ImageDraw.Draw(img)
    pal = get_palette()
    pad_x, pad_y, line_gap = 36, 20, 8

    text = headline.upper().strip()
    max_w = canvas_w - 2 * SIDE_MARGIN - 2 * pad_x
    font, lines = _fit_lines(text, max_w, start=font_size, min_size=40, max_lines=2)
    asc, desc, lh = _line_height(font)

    text_w = max(_tw(font, ln) for ln in lines)
    card_w = text_w + 2 * pad_x
    card_h = len(lines) * lh + (len(lines) - 1) * line_gap + 2 * pad_y
    left = (canvas_w - card_w) / 2
    top = HEADLINE_Y

    draw.rounded_rectangle([left, top, left + card_w, top + card_h], radius=16, fill=pal["accent"])
    base = top + pad_y + asc
    for ln in lines:
        draw.text((canvas_w / 2, base), ln, font=font, fill=pal["accent_fg"], anchor="ms")
        base += lh + line_gap
    return np.array(img)


# --------------------------------------------------------------------------- kartu CTA brand

def _trim_margins(img: Image.Image, tolerance: int = 12) -> Image.Image:
    """Buang margin polos (putih atau transparan) di sekeliling logo supaya mengisi lingkaran."""
    rgba = img.convert("RGBA")
    flat = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    flat.alpha_composite(rgba)
    diff = ImageChops.difference(flat.convert("RGB"), Image.new("RGB", rgba.size, (255, 255, 255)))
    bbox = diff.point(lambda v: 255 if v > tolerance else 0).getbbox()
    return rgba.crop(bbox) if bbox else rgba


def _logo_badge(diameter: int, pal: Dict[str, RGBA], brand: dict, fallback_letter: str) -> Image.Image:
    """Lingkaran berisi logo brand (assets/logo.png). Tanpa logo -> huruf pertama nama brand."""
    ring = 6
    badge = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    d = ImageDraw.Draw(badge)

    logo_img: Optional[Image.Image] = None
    logo_rel = brand.get("logo_path")
    if logo_rel:
        p = config.ROOT / logo_rel
        if p.is_file():
            try:
                logo_img = _trim_margins(Image.open(p).convert("RGBA"))
            except Exception:  # noqa: BLE001
                logo_img = None

    if logo_img is not None:
        d.ellipse([0, 0, diameter - 1, diameter - 1], fill=pal["accent"])
        inner = diameter - 2 * ring
        d.ellipse([ring, ring, ring + inner - 1, ring + inner - 1], fill=(255, 255, 255, 255))
        box = int(inner * 0.86)
        logo_img.thumbnail((box, box), Image.LANCZOS)
        mask = Image.new("L", (diameter, diameter), 0)
        ImageDraw.Draw(mask).ellipse([ring, ring, ring + inner - 1, ring + inner - 1], fill=255)
        layer = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
        layer.paste(logo_img, ((diameter - logo_img.width) // 2, (diameter - logo_img.height) // 2), logo_img)
        badge.paste(layer, (0, 0), Image.composite(layer.split()[3], Image.new("L", layer.size, 0), mask))
    else:
        d.ellipse([0, 0, diameter - 1, diameter - 1], fill=pal["accent"])
        font = get_font(int(diameter * 0.55))
        d.text((diameter / 2, diameter / 2), fallback_letter, font=font, fill=pal["accent_fg"], anchor="mm")
    return badge


def create_branded_outro_frame(
    brand_config: Optional[Dict[str, Any]] = None,
    canvas_w: int = CANVAS_WIDTH,
    canvas_h: int = CANVAS_HEIGHT,
    cta_text: Optional[str] = None,
    opaque_background: bool = False,
) -> np.ndarray:
    """Kartu CTA brand: logo, nama, tagline, kontak, dan tombol ajakan.

    Default transparan (overlay di atas B-roll, subtitle tetap tampil di bawahnya).
    Semua isi dari brand.json; `cta_text` (mis. headline scene CTA) menjadi teks tombol.
    Seluruh teks dimuat ke dalam kartu (shrink / wrap / elipsis).
    """
    brand = brand_config if brand_config is not None else load_brand()
    pal = get_palette(brand)
    bg = pal["primary"] if opaque_background else (0, 0, 0, 0)
    img = _blank(canvas_w, canvas_h, bg)
    draw = ImageDraw.Draw(img)

    panel_w = canvas_w - 2 * 90
    inner_w = panel_w - 2 * 48
    left = (canvas_w - panel_w) // 2
    top = 300
    cx = canvas_w / 2

    company = str(brand.get("company") or (brand.get("chrome") or {}).get("brand_text") or "").strip().upper()
    tagline = str(brand.get("tagline") or brand.get("industry") or "").strip().rstrip(" .")
    footer = (brand.get("chrome") or {}).get("footer") or {}
    contacts = [str(x).strip() for x in (footer.get("lines") or []) if str(x).strip()] if footer.get("show", True) else []
    contacts = contacts[:3]
    cta = " ".join((cta_text or "").split()).upper()

    name_font, name_lines = _fit_lines(company, inner_w, start=76, min_size=44, max_lines=1) if company else (None, [])
    tag_font, tag_lines = _fit_lines(tagline, inner_w, start=32, min_size=26, max_lines=2, regular=True) if tagline else (None, [])
    cta_font, cta_lines = (_fit_lines(cta, inner_w - 80, start=44, min_size=30, max_lines=1) if cta else (None, []))
    contact_font = get_font(38, regular=True)

    logo_d, pad_top, gap = 170, 44, 22
    pill_h, pill_gap, btn_h = 64, 14, 82

    # ---- ukur tinggi total
    h = pad_top + logo_d
    if name_lines:
        h += gap + _line_height(name_font)[2]
    if tag_lines:
        h += 10 + len(tag_lines) * (_line_height(tag_font)[2] + 4)
    if contacts:
        h += gap + 4 + gap + len(contacts) * pill_h + (len(contacts) - 1) * pill_gap
    if cta_lines:
        h += gap + btn_h
    h += pad_top
    panel = [left, top, left + panel_w, top + h]

    draw.rounded_rectangle(panel, radius=44, fill=_shade(pal["primary"], 0.92, alpha=225),
                           outline=_shade(pal["accent"], 1.0, alpha=170), width=2)

    y = top + pad_top
    badge = _logo_badge(logo_d, pal, brand, (company[:1] or "?"))
    img.alpha_composite(badge, (int(cx - logo_d / 2), int(y)))
    y += logo_d

    if name_lines:
        y += gap
        asc, _, lh = _line_height(name_font)
        draw.text((cx, y + asc), name_lines[0], font=name_font, fill=pal["fg"], anchor="ms")
        y += lh

    if tag_lines:
        y += 10
        asc, _, lh = _line_height(tag_font)
        for ln in tag_lines:
            draw.text((cx, y + asc), ln, font=tag_font, fill=_shade(pal["fg"], 1.0, alpha=215), anchor="ms")
            y += lh + 4

    if contacts:
        y += gap
        draw.line([(cx - 120, y + 2), (cx + 120, y + 2)], fill=pal["accent"], width=4)
        y += 4 + gap
        for line in contacts:
            c_font, c_lines = _fit_lines(line, inner_w - 80, start=38, min_size=26, max_lines=1, regular=True)
            text = c_lines[0]
            pw = min(inner_w, max(360, _tw(c_font, text) + 80))
            box = [cx - pw / 2, y, cx + pw / 2, y + pill_h]
            draw.rounded_rectangle(box, radius=pill_h // 2, fill=_shade(pal["primary"], 1.18, alpha=235),
                                   outline=pal["accent"], width=2)
            asc, desc, lh = _line_height(c_font)
            draw.text((cx, y + (pill_h - lh) / 2 + asc), text, font=c_font, fill=pal["fg"], anchor="ms")
            y += pill_h + pill_gap
        y -= pill_gap

    if cta_lines:
        y += gap
        text = cta_lines[0]
        bw = min(inner_w, _tw(cta_font, text) + 80)
        box = [cx - bw / 2, y, cx + bw / 2, y + btn_h]
        draw.rounded_rectangle(box, radius=btn_h // 2, fill=pal["accent"])
        asc, desc, lh = _line_height(cta_font)
        draw.text((cx, y + (btn_h - lh) / 2 + asc), text, font=cta_font, fill=pal["accent_fg"], anchor="ms")

    return np.array(img)
