"""Layout: tipografi_minimal. Menampilkan tipografi bersih, elegan, dengan fokus maksimal pada pesan."""
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

from src.carousel.layouts.base import (
    H, MARGIN, W, create_base_canvas, draw_header, fit_text,
    get_font_path, to_hex
)

LAYOUT_ID = "tipografi_minimal"


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

    C = brand["colors"]
    text_c = to_hex(C["text_on_primary"])
    sec_c = to_hex(C["secondary"])
    acc_c = to_hex(C["accent"])

    max_w = W - 2 * MARGIN
    limit_bottom = H - 220

    # Clean centered-vertical typography block
    y_target = 340
    h_font, h_lines, h_lh, h_fit, h_size = fit_text(draw, headline, bold, max_w, 360, 84, 56, spacing=1.18)
    sub_gap = 40
    s_font, s_lines, s_lh, s_fit, s_size = fit_text(draw, subtext, reg, max_w, 300, 44, 30, spacing=1.3)

    block_h = h_lh * len(h_lines) + sub_gap + s_lh * len(s_lines)
    y = max(y_target, int((limit_bottom + 180 - block_h) * 0.45))

    for line in h_lines:
        draw.text((MARGIN, y), line, font=h_font, fill=text_c)
        y += h_lh

    y += 24
    draw.rectangle([MARGIN, y, MARGIN + 120, y + 8], fill=acc_c)
    y += sub_gap

    for line in s_lines:
        draw.text((MARGIN, y), line, font=s_font, fill=sec_c)
        y += s_lh

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)

    return {
        "layout_id": LAYOUT_ID,
        "path": str(out_path),
        "has_photo": False,
        "photo_path": None,
        "text_bottom": y,
        "limit_bottom": limit_bottom,
        "overflow": not (h_fit and s_fit),
        "headline_size": h_size,
        "subtext_size": s_size,
    }
