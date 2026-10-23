"""Base utilities, constants, font loader, and rendering helpers for parametric layouts."""
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageFont

from src import config

W, H, MARGIN = 1080, 1350, 80


def to_hex(c: str, alpha: int = 255) -> tuple[int, int, int, int]:
    """Convert hex color string to RGBA tuple."""
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha)


def darker(rgb: tuple[int, ...], factor: float = 0.6) -> tuple[int, int, int]:
    """Return darker version of an RGB tuple."""
    return tuple(int(v * factor) for v in rgb[:3])


def get_font_path(brand: dict[str, Any], bold: bool = True) -> str:
    """Return explicit font path from repo assets or brand config, removing system font dependency."""
    key = "font_path" if bold else "font_regular_path"
    configured = brand.get(key)
    if configured and (config.ROOT / configured).is_file():
        return str(config.ROOT / configured)

    # Fallback directly to repo-bundled fonts
    default_filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    bundled = config.ROOT / "assets" / "fonts" / default_filename
    if bundled.is_file():
        return str(bundled)

    raise FileNotFoundError(f"Font file not found in repo: {bundled}")


def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load FreeTypeFont at specified size."""
    return ImageFont.truetype(path, size)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: Any, max_w: int) -> list[str]:
    """Wrap text into lines that do not exceed max_w."""
    lines: list[str] = []
    cur = ""
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


def fit_text(draw: ImageDraw.ImageDraw, text: str, font_path: str,
             max_w: int, max_h: int, start_size: int, min_size: int,
             spacing: float = 1.18) -> tuple[Any, list[str], int, bool, int]:
    """Scale font down until text fits max_w and max_h. Return (font, lines, line_h, fits, size)."""
    size = start_size
    while True:
        font = load_font(font_path, size)
        lines = wrap_text(draw, text, font, max_w)
        line_h = int(size * spacing)
        h = line_h * len(lines)
        widest = max((draw.textlength(l, font=font) for l in lines), default=0)
        fits = h <= max_h and widest <= max_w
        if fits or size <= min_size:
            return font, lines, line_h, fits, size
        size -= 4


def create_base_canvas(brand: dict[str, Any]) -> Image.Image:
    """Create background gradient with subtle brand accents."""
    primary_c = brand["colors"]["primary"]
    top = to_hex(primary_c)
    bot = darker(top, 0.62)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)))
    img = img.convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.ellipse([W - 420, -260, W + 280, 440], fill=to_hex(brand["colors"]["accent"], 34))
    od.ellipse([-320, H - 520, 380, H + 180], fill=to_hex(brand["colors"]["secondary"], 16))
    return Image.alpha_composite(img, ov)


def draw_header(img: Image.Image, draw: ImageDraw.ImageDraw, brand: dict[str, Any],
                bold_font: str, reg_font: str, index: int = 1, total: int = 1) -> None:
    """Draw brand wordmark/logo and slide index header."""
    logo_p = config.ROOT / brand.get("logo_path", "")
    if logo_p.is_file():
        try:
            logo = Image.open(logo_p).convert("RGBA")
            logo = logo.resize((int(logo.width * 56 / logo.height), 56))
            img.paste(logo, (MARGIN, 64), logo)
        except Exception:
            _draw_text_wordmark(draw, brand, bold_font)
    else:
        _draw_text_wordmark(draw, brand, bold_font)

    if total > 1:
        sec_c = to_hex(brand["colors"]["secondary"])
        draw.text((W - MARGIN, 70), f"{index}/{total}", font=load_font(reg_font, 30), fill=sec_c, anchor="ra")


def _draw_text_wordmark(draw: ImageDraw.ImageDraw, brand: dict[str, Any], bold_font: str) -> None:
    acc = to_hex(brand["colors"]["accent"])
    draw.rectangle([MARGIN, 76, MARGIN + 22, 98], fill=acc)
    draw.text((MARGIN + 36, 70), brand.get("company", "").upper(), font=load_font(bold_font, 32),
              fill=to_hex(brand["colors"]["text_on_primary"]))


def paste_photo(img: Image.Image, photo_path: str | None, frac: float = 0.42,
                max_w_frac: float = 0.55, align: str = "right_bottom") -> tuple[int, bool]:
    """Paste cutout photo onto image. Return (photo_top_y, has_photo)."""
    if not photo_path or not Path(photo_path).is_file():
        return H, False
    try:
        ph = Image.open(photo_path).convert("RGBA")
        th = int(H * frac)
        ph = ph.resize((int(ph.width * th / ph.height), th))
        if ph.width > int(W * max_w_frac):
            ph = ph.resize((int(W * max_w_frac), int(ph.height * W * max_w_frac / ph.width)))

        if align == "right_bottom":
            x, y = W - ph.width - 30, H - ph.height
        elif align == "center_bottom":
            x, y = (W - ph.width) // 2, H - ph.height
        elif align == "left_bottom":
            x, y = MARGIN, H - ph.height
        else:
            x, y = W - ph.width - 30, H - ph.height

        img.paste(ph, (x, y), ph)
        return y, True
    except Exception:
        return H, False
