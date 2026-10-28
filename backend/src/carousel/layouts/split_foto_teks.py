"""Layout: split_foto_teks. Menampilkan pembagian tegas teks di sisi kiri dan foto di sisi kanan."""
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

from src.carousel.layouts.base import (
    H, MARGIN, W, create_base_canvas, draw_header, fit_text,
    get_font_path, paste_photo, to_hex
)

LAYOUT_ID = "split_foto_teks"


def render(text: dict[str, str], photo_path: str | None, brand: dict[str, Any],
           params: dict[str, Any], out_path: str | Path) -> dict[str, Any]:
    headline = text.get("headline", "")
    subtext = text.get("subtext", "")

    bold = get_font_path(brand, bold=True)
    reg = get_font_path(brand, bold=False)

    img = create_base_canvas(brand)
    draw = ImageDraw.Draw(img)

    index = params.get("index", 1)
    total = params.get("total", 1)
    draw_header(img, draw, brand, bold, reg, index=index, total=total)

    photo_top, has_photo = paste_photo(img, photo_path, frac=0.48, max_w_frac=0.52)
    draw = ImageDraw.Draw(img)

    C = brand["colors"]
    text_c = to_hex(C["text_on_primary"])
    sec_c = to_hex(C["secondary"])
    acc_c = to_hex(C["accent"])

    y = 210
    max_w = (W - 2 * MARGIN) if not has_photo else int(W * 0.48)
    limit_bottom = H - 180

    h_font, h_lines, h_lh, h_fit, h_size = fit_text(draw, headline, bold, max_w, 380, 74, 50)
    for line in h_lines:
        draw.text((MARGIN, y), line, font=h_font, fill=text_c)
        y += h_lh

    y += 24
    draw.rectangle([MARGIN, y, MARGIN + 90, y + 6], fill=acc_c)
    y += 34

    s_font, s_lines, s_lh, s_fit, s_size = fit_text(draw, subtext, reg, max_w, limit_bottom - y, 40, 28, 1.3)
    for line in s_lines:
        draw.text((MARGIN, y), line, font=s_font, fill=sec_c)
        y += s_lh

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)

    return {
        "layout_id": LAYOUT_ID,
        "path": str(out_path),
        "has_photo": has_photo,
        "photo_path": photo_path if has_photo else None,
        "text_bottom": y,
        "limit_bottom": limit_bottom,
        "overflow": not (h_fit and s_fit),
        "headline_size": h_size,
        "subtext_size": s_size,
    }
