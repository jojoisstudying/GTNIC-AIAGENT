"""Layout: cta_blok. Slide penutup dengan blok ajakan bertindak (CTA) yang mencolok."""
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

from src.carousel.layouts.base import (
    H, MARGIN, W, create_base_canvas, draw_header, fit_text,
    get_font_path, load_font, paste_photo, to_hex
)

LAYOUT_ID = "cta_blok"


def render(text: dict[str, str], photo_path: str | None, brand: dict[str, Any],
           params: dict[str, Any], out_path: str | Path) -> dict[str, Any]:
    headline = text.get("headline", "")
    subtext = text.get("subtext", "")
    button_label = params.get("button_label") or "Simpan  •  Bagikan  •  Ikuti"

    bold = get_font_path(brand, bold=True)
    reg = get_font_path(brand, bold=False)

    img = create_base_canvas(brand)
    draw = ImageDraw.Draw(img)

    index = params.get("index", 1)
    total = params.get("total", 1)
    draw_header(img, draw, brand, bold, reg, index=index, total=total)

    photo_top, has_photo = paste_photo(img, photo_path, frac=0.40)
    draw = ImageDraw.Draw(img)

    C = brand["colors"]
    text_c = to_hex(C["text_on_primary"])
    sec_c = to_hex(C["secondary"])
    acc_c = to_hex(C["accent"])

    max_w = (W - 2 * MARGIN) if not has_photo else (W - MARGIN - 360)
    limit_bottom = photo_top - 30 if has_photo else H - 240

    y = 260
    h_font, h_lines, h_lh, h_fit, h_size = fit_text(draw, headline, bold, max_w, 280, 78, 52)
    for line in h_lines:
        draw.text((MARGIN, y), line, font=h_font, fill=text_c)
        y += h_lh

    y += 24
    draw.rectangle([MARGIN, y, MARGIN + 120, y + 8], fill=acc_c)
    y += 38

    s_font, s_lines, s_lh, s_fit, s_size = fit_text(draw, subtext, reg, max_w, limit_bottom - y - 140, 42, 30, 1.3)
    for line in s_lines:
        draw.text((MARGIN, y), line, font=s_font, fill=sec_c)
        y += s_lh

    # Distinctive CTA Button Block
    y += 50
    f = load_font(bold, 36)
    bw = int(draw.textlength(button_label, font=f)) + 90
    bw = min(bw, max_w)
    draw.rounded_rectangle([MARGIN, y, MARGIN + bw, y + 96], radius=48, fill=acc_c)
    draw.text((MARGIN + bw // 2, y + 48), button_label, font=f, fill=to_hex(C["primary"]), anchor="mm")
    text_bottom = y + 96

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)

    return {
        "layout_id": LAYOUT_ID,
        "path": str(out_path),
        "has_photo": has_photo,
        "photo_path": photo_path if has_photo else None,
        "text_bottom": text_bottom,
        "limit_bottom": limit_bottom,
        "overflow": not (h_fit and s_fit),
        "headline_size": h_size,
        "subtext_size": s_size,
    }
