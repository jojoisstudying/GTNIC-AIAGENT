"""Layout: perbandingan. Menampilkan perbandingan dua hal (A vs B, Sebelum vs Sesudah, atau Cara Lama vs Baru)."""
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

from src.carousel.layouts.base import (
    H, MARGIN, W, create_base_canvas, draw_header, fit_text,
    get_font_path, load_font, to_hex, wrap_text
)

LAYOUT_ID = "perbandingan"


def render(text: dict[str, str], photo_path: str | None, brand: dict[str, Any],
           params: dict[str, Any], out_path: str | Path) -> dict[str, Any]:
    headline = text.get("headline", "")
    subtext = text.get("subtext", "")
    left_title = params.get("left_title") or "Cara Biasa"
    right_title = params.get("right_title") or "Cara Efektif"
    left_text = params.get("left_text") or subtext
    right_text = params.get("right_text") or "Fokus pada konsistensi dan hasil yang terukur."

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

    y = 200
    max_w = W - 2 * MARGIN
    h_font, h_lines, h_lh, h_fit, h_size = fit_text(draw, headline, bold, max_w, 180, 64, 46)
    for line in h_lines:
        draw.text((MARGIN, y), line, font=h_font, fill=text_c)
        y += h_lh

    y += 40
    # Two cards side by side
    col_w = (W - 2 * MARGIN - 40) // 2
    card_h = 580

    card_ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card_ov)

    # Left card
    cd.rounded_rectangle([MARGIN, y, MARGIN + col_w, y + card_h],
                         radius=24, fill=(11, 42, 91, 190), outline=(200, 200, 200, 70), width=2)
    # Right card (highlighted with accent)
    cd.rounded_rectangle([MARGIN + col_w + 40, y, MARGIN + 2 * col_w + 40, y + card_h],
                         radius=24, fill=(11, 42, 91, 230), outline=to_hex(C["accent"], 180), width=3)
    img = Image.alpha_composite(img, card_ov)
    draw = ImageDraw.Draw(img)

    title_f = load_font(bold, 36)
    txt_f = load_font(reg, 30)

    # Draw left column
    draw.text((MARGIN + 24, y + 30), left_title, font=title_f, fill=sec_c)
    draw.line([MARGIN + 24, y + 80, MARGIN + col_w - 24, y + 80], fill=(200, 200, 200, 100), width=2)
    wrapped_l = wrap_text(draw, left_text, txt_f, col_w - 48)
    cy = y + 100
    for l in wrapped_l:
        draw.text((MARGIN + 24, cy), l, font=txt_f, fill=sec_c)
        cy += 40

    # Draw right column
    rx = MARGIN + col_w + 40
    draw.text((rx + 24, y + 30), right_title, font=title_f, fill=acc_c)
    draw.line([rx + 24, y + 80, rx + col_w - 24, y + 80], fill=acc_c, width=2)
    wrapped_r = wrap_text(draw, right_text, txt_f, col_w - 48)
    cy = y + 100
    for l in wrapped_r:
        draw.text((rx + 24, cy), l, font=txt_f, fill=text_c)
        cy += 40

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)

    return {
        "layout_id": LAYOUT_ID,
        "path": str(out_path),
        "has_photo": False,
        "photo_path": None,
        "text_bottom": y + card_h,
        "limit_bottom": H - 150,
        "overflow": not h_fit,
        "headline_size": h_size,
        "subtext_size": 30,
    }
