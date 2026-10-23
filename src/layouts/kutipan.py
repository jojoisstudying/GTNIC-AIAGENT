"""Layout: kutipan. Menampilkan kutipan besar dengan tanda kutip raksasa dan atribusi."""
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

from src.layouts.base import (
    H, MARGIN, W, create_base_canvas, draw_header, fit_text,
    get_font_path, load_font, paste_photo, to_hex
)

LAYOUT_ID = "kutipan"


def render(text: dict[str, str], photo_path: str | None, brand: dict[str, Any],
           params: dict[str, Any], out_path: str | Path) -> dict[str, Any]:
    headline = text.get("headline", "")
    subtext = text.get("subtext", "")
    author = params.get("author") or brand.get("company", "")

    bold = get_font_path(brand, bold=True)
    reg = get_font_path(brand, bold=False)

    img = create_base_canvas(brand)
    draw = ImageDraw.Draw(img)

    index = params.get("index", 1)
    total = params.get("total", 1)
    draw_header(img, draw, brand, bold, reg, index=index, total=total)

    photo_top, has_photo = paste_photo(img, photo_path, frac=0.36)
    draw = ImageDraw.Draw(img)

    C = brand["colors"]
    text_c = to_hex(C["text_on_primary"])
    sec_c = to_hex(C["secondary"])
    acc_c = to_hex(C["accent"])

    y = 220
    # Giant quote symbol
    q_font = load_font(bold, 180)
    draw.text((MARGIN - 10, y), "“", font=q_font, fill=acc_c)
    y += 120

    max_w = (W - 2 * MARGIN) if not has_photo else (W - MARGIN - 360)
    limit_bottom = photo_top - 30 if has_photo else H - 200

    h_font, h_lines, h_lh, h_fit, h_size = fit_text(draw, f'"{headline}"', bold, max_w, 360, 68, 48, spacing=1.2)
    for line in h_lines:
        draw.text((MARGIN, y), line, font=h_font, fill=text_c)
        y += h_lh

    y += 30
    draw.rectangle([MARGIN, y, MARGIN + 80, y + 4], fill=acc_c)
    y += 30

    # Subtext / Context
    if subtext:
        s_font, s_lines, s_lh, s_fit, s_size = fit_text(draw, subtext, reg, max_w, 200, 36, 26, spacing=1.25)
        for line in s_lines:
            draw.text((MARGIN, y), line, font=s_font, fill=sec_c)
            y += s_lh
        y += 20
    else:
        s_fit, s_size = True, 0

    # Author
    if author:
        auth_font = load_font(bold, 32)
        draw.text((MARGIN, y), f"— {author}", font=auth_font, fill=acc_c)
        y += 45

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
