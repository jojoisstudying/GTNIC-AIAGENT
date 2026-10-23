"""Compositing deterministik: teks, font, logo, warna SELALU dari brand kit, bukan dari AI.
Layout per role slide: cover / single / content / cta. Teks otomatis dikecilkan agar muat."""
import glob
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src import config

W, H, MARGIN = 1080, 1350, 80

BOLD_FALLBACKS = ["/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf"]
REG_FALLBACKS = ["/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf"]


def _hex(c: str, alpha: int = 255):
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha)


def _darker(rgb, f=0.6):
    return tuple(int(v * f) for v in rgb[:3])


def _font_path(brand: dict, bold: bool) -> str | None:
    key = "font_path" if bold else "font_regular_path"
    cands = []
    if brand.get(key):
        cands.append(str(config.ROOT / brand[key]))
    cands += BOLD_FALLBACKS if bold else REG_FALLBACKS
    cands += sorted(glob.glob("/usr/share/fonts/**/*.ttf", recursive=True))[:1]
    for p in cands:
        if Path(p).is_file():
            return p
    return None


def _load(path, size):
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_text(draw, text, path, max_w, max_h, start, min_size, spacing=1.18):
    """Kecilkan font bertahap sampai teks muat. Return (font, lines, line_h, muat?, ukuran)."""
    size = start
    while True:
        font = _load(path, size)
        lines = _wrap(draw, text, font, max_w)
        line_h = int(size * spacing)
        h = line_h * len(lines)
        widest = max((draw.textlength(l, font=font) for l in lines), default=0)
        fits = h <= max_h and widest <= max_w
        if fits or size <= min_size:
            return font, lines, line_h, fits, size
        size -= 4


def _background(brand):
    top, bot = _hex(brand["colors"]["primary"]), _darker(_hex(brand["colors"]["primary"]), 0.62)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)))
    img = img.convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.ellipse([W - 420, -260, W + 280, 440], fill=_hex(brand["colors"]["accent"], 34))
    od.ellipse([-320, H - 520, 380, H + 180], fill=_hex(brand["colors"]["secondary"], 16))
    return Image.alpha_composite(img, ov)


def _wordmark(img, draw, brand, bold):
    logo_p = config.ROOT / brand.get("logo_path", "")
    if logo_p.is_file():
        logo = Image.open(logo_p).convert("RGBA")
        logo = logo.resize((int(logo.width * 56 / logo.height), 56))
        img.paste(logo, (MARGIN, 64), logo)
        return
    acc = _hex(brand["colors"]["accent"])
    draw.rectangle([MARGIN, 76, MARGIN + 22, 98], fill=acc)
    draw.text((MARGIN + 36, 70), brand.get("company", "").upper(), font=_load(bold, 32),
              fill=_hex(brand["colors"]["text_on_primary"]))


def _photo(img, photo_path, frac):
    """Tempel foto cutout di kanan-bawah. Return (photo_top atau H, ada foto?)."""
    if not photo_path or not Path(photo_path).is_file():
        return H, False
    ph = Image.open(photo_path).convert("RGBA")
    th = int(H * frac)
    ph = ph.resize((int(ph.width * th / ph.height), th))
    if ph.width > int(W * 0.55):
        ph = ph.resize((int(W * 0.55), int(ph.height * W * 0.55 / ph.width)))
    img.paste(ph, (W - ph.width - 30, H - ph.height), ph)
    return H - ph.height, True


def render_slide(role, headline, subtext, photo_path, brand, out_path, index=1, total=1, step_no=0) -> dict:
    C = brand["colors"]
    bold, reg = _font_path(brand, True), _font_path(brand, False)
    img = _background(brand)
    draw = ImageDraw.Draw(img)
    text_c, sec_c, acc_c = _hex(C["text_on_primary"]), _hex(C["secondary"]), _hex(C["accent"])
    max_w = W - 2 * MARGIN

    _wordmark(img, draw, brand, bold)
    if total > 1:
        draw.text((W - MARGIN, 70), f"{index}/{total}", font=_load(reg, 30), fill=sec_c, anchor="ra")

    frac = {"cover": 0.46, "single": 0.46, "content": 0.38, "cta": 0.40}.get(role, 0.42)
    # watermark nomor besar bila tidak ada foto (slide content)
    if role == "content" and not (photo_path and Path(photo_path).is_file()) and step_no:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ov).text((W - 40, H - 40), f"{step_no:02d}", font=_load(bold, 460),
                                fill=_hex(C["secondary"], 22), anchor="rd")
        img = Image.alpha_composite(img, ov)
        draw = ImageDraw.Draw(img)

    photo_top, has_photo = _photo(img, photo_path, frac)
    draw = ImageDraw.Draw(img)
    limit_bottom = (photo_top - 30) if has_photo else (H - 200)
    reserve = 150 if role == "cta" else 0           # ruang tombol CTA
    y = 190

    if role == "content" and step_no:               # badge nomor langkah
        draw.rounded_rectangle([MARGIN, y, MARGIN + 116, y + 116], radius=26, fill=acc_c)
        draw.text((MARGIN + 58, y + 58), f"{step_no:02d}", font=_load(bold, 60),
                  fill=_hex(C["primary"]), anchor="mm")
        y += 156

    h_start, h_min = (96, 56) if role in ("cover", "single") else (78, 54)
    y0 = y
    h_font, h_lines, h_lh, h_fit, h_size = fit_text(draw, headline, bold, max_w,
                                                    min(400, limit_bottom - reserve - y0 - 150), h_start, h_min)
    sub_gap = 22 + 8 + 38                           # jarak headline -> garis aksen -> subtext
    s_font, s_lines, s_lh, s_fit, s_size = fit_text(draw, subtext, reg, max_w,
                                                    limit_bottom - reserve - (y0 + h_lh * len(h_lines) + sub_gap),
                                                    42, 30, 1.3)
    block = h_lh * len(h_lines) + sub_gap + s_lh * len(s_lines) + (130 if role == "cta" else 0)
    if not has_photo and role in ("cta", "cover", "single"):   # tanpa foto: turunkan blok teks agar seimbang
        y = y0 + max(0, int((limit_bottom - y0 - block) * 0.4))
    for line in h_lines:
        draw.text((MARGIN, y), line, font=h_font, fill=text_c)
        y += h_lh
    y += 22
    draw.rectangle([MARGIN, y, MARGIN + 120, y + 8], fill=acc_c)
    y += 38
    for line in s_lines:
        draw.text((MARGIN, y), line, font=s_font, fill=sec_c)
        y += s_lh
    text_bottom = y

    if role == "cta":                               # tombol ajakan
        label = "Simpan  •  Bagikan  •  Ikuti"
        f = _load(bold, 38)
        bw = int(draw.textlength(label, font=f)) + 80
        by = text_bottom + 40
        draw.rounded_rectangle([MARGIN, by, MARGIN + bw, by + 90], radius=45, fill=acc_c)
        draw.text((MARGIN + bw // 2, by + 45), label, font=f, fill=_hex(C["primary"]), anchor="mm")
        text_bottom = by + 90
    if role == "cover" and total > 1:               # petunjuk geser
        f = _load(bold, 34)
        draw.rounded_rectangle([MARGIN, H - 170, MARGIN + 230, H - 106], radius=32, outline=acc_c, width=4)
        draw.text((MARGIN + 115, H - 138), "Geser  →", font=f, fill=acc_c, anchor="mm")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)
    return {"role": role, "index": index, "path": str(out_path), "has_photo": has_photo,
            "photo_path": photo_path if has_photo else None, "text_bottom": text_bottom,
            "limit_bottom": limit_bottom + reserve, "overflow": not (h_fit and s_fit),
            "headline_size": h_size, "subtext_size": s_size}