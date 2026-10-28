"""Layout: daftar_bernomor. Menampilkan daftar poin-poin bernomor rapi."""
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

from src.carousel.layouts.base import (
    H, MARGIN, W, create_base_canvas, draw_header, fit_text,
    get_font_path, load_font, paste_photo, to_hex, wrap_text
)

LAYOUT_ID = "daftar_bernomor"


def render(text: dict[str, str], photo_path: str | None, brand: dict[str, Any],
           params: dict[str, Any], out_path: str | Path) -> dict[str, Any]:
    headline = text.get("headline", "")
    subtext = text.get("subtext", "")
    items = params.get("items") or []
    if not items and subtext:
        # Split subtext by periods, bullet points, or semicolons if explicit items not passed
        parts = [p.strip() for p in subtext.replace(";", ".").split(".") if p.strip()]
        items = parts[:3] if parts else [subtext]

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

    y = 200
    max_w = (W - 2 * MARGIN) if not has_photo else (W - MARGIN - 360)
    limit_bottom = photo_top - 30 if has_photo else H - 180

    h_font, h_lines, h_lh, h_fit, h_size = fit_text(draw, headline, bold, max_w, 200, 68, 48)
    for line in h_lines:
        draw.text((MARGIN, y), line, font=h_font, fill=text_c)
        y += h_lh

    y += 20
    draw.rectangle([MARGIN, y, MARGIN + 100, y + 6], fill=acc_c)
    y += 40

    item_num_f = load_font(bold, 36)
    item_txt_f = load_font(reg, 32)
    s_fit = True
    s_size = 32

    for idx, item in enumerate(items, 1):
        if y >= limit_bottom - 60:
            s_fit = False
            break
        # Number badge
        draw.ellipse([MARGIN, y, MARGIN + 48, y + 48], fill=acc_c)
        draw.text((MARGIN + 24, y + 24), str(idx), font=item_num_f, fill=to_hex(C["primary"]), anchor="mm")

        # Item text lines
        wrapped = wrap_text(draw, item, item_txt_f, max_w - 70)
        item_y = y + 4
        for wline in wrapped:
            draw.text((MARGIN + 70, item_y), wline, font=item_txt_f, fill=sec_c)
            item_y += 40
        y = max(item_y + 16, y + 64)

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
