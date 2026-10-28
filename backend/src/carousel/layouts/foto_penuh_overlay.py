"""Layout: foto_penuh_overlay. Foto besar di latar dengan card overlay semi-transparan untuk teks."""
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

from src.carousel.layouts.base import (
    H, MARGIN, W, create_base_canvas, draw_header, fit_text,
    get_font_path, paste_photo, to_hex
)

LAYOUT_ID = "foto_penuh_overlay"


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

    photo_top, has_photo = paste_photo(img, photo_path, frac=0.60, max_w_frac=0.75, align="center_bottom")

    C = brand["colors"]
    text_c = to_hex(C["text_on_primary"])
    sec_c = to_hex(C["secondary"])
    acc_c = to_hex(C["accent"])

    # Draw semi-transparent card overlay over the lower middle part
    card_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card_overlay)
    card_y = 220
    card_h = 480
    card_draw.rounded_rectangle([MARGIN - 20, card_y, W - MARGIN + 20, card_y + card_h],
                                 radius=32, fill=(11, 42, 91, 210), outline=to_hex(C["accent"], 120), width=2)
    img = Image.alpha_composite(img, card_overlay)
    draw = ImageDraw.Draw(img)

    y = card_y + 40
    max_w = W - 2 * MARGIN - 40
    h_font, h_lines, h_lh, h_fit, h_size = fit_text(draw, headline, bold, max_w, 200, 64, 46)
    for line in h_lines:
        draw.text((MARGIN + 10, y), line, font=h_font, fill=text_c)
        y += h_lh

    y += 18
    draw.rectangle([MARGIN + 10, y, MARGIN + 90, y + 6], fill=acc_c)
    y += 28

    s_font, s_lines, s_lh, s_fit, s_size = fit_text(draw, subtext, reg, max_w, 180, 38, 26, 1.25)
    for line in s_lines:
        draw.text((MARGIN + 10, y), line, font=s_font, fill=sec_c)
        y += s_lh

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)

    return {
        "layout_id": LAYOUT_ID,
        "path": str(out_path),
        "has_photo": has_photo,
        "photo_path": photo_path if has_photo else None,
        "text_bottom": y,
        "limit_bottom": card_y + card_h,
        "overflow": not (h_fit and s_fit),
        "headline_size": h_size,
        "subtext_size": s_size,
    }
