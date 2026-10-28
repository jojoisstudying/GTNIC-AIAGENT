"""Layout: langkah_diagram. Menampilkan alur diagram 3 langkah vertikal secara jelas."""
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

from src.carousel.layouts.base import (
    H, MARGIN, W, create_base_canvas, draw_header, fit_text,
    get_font_path, load_font, to_hex, wrap_text
)

LAYOUT_ID = "langkah_diagram"


def render(text: dict[str, str], photo_path: str | None, brand: dict[str, Any],
           params: dict[str, Any], out_path: str | Path) -> dict[str, Any]:
    headline = text.get("headline", "")
    subtext = text.get("subtext", "")
    steps = params.get("steps") or []
    if not steps and subtext:
        parts = [p.strip() for p in subtext.replace(";", ".").split(".") if p.strip()]
        steps = parts[:3] if parts else [subtext]

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

    y += 24
    draw.rectangle([MARGIN, y, MARGIN + 80, y + 6], fill=acc_c)
    y += 50

    step_num_f = load_font(bold, 34)
    step_txt_f = load_font(reg, 32)
    step_box_w = max_w - 90

    for i, step_desc in enumerate(steps, 1):
        # Step node
        draw.ellipse([MARGIN, y, MARGIN + 60, y + 60], fill=acc_c)
        draw.text((MARGIN + 30, y + 30), str(i), font=step_num_f, fill=to_hex(C["primary"]), anchor="mm")

        # Vertical connecting line to next step
        if i < len(steps):
            draw.line([MARGIN + 30, y + 60, MARGIN + 30, y + 170], fill=to_hex(C["accent"], 140), width=4)

        # Step description
        wrapped = wrap_text(draw, step_desc, step_txt_f, step_box_w)
        sy = y + 8
        for wline in wrapped:
            draw.text((MARGIN + 85, sy), wline, font=step_txt_f, fill=sec_c)
            sy += 40

        y += max(130, (len(wrapped) * 40 + 50))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=92)

    return {
        "layout_id": LAYOUT_ID,
        "path": str(out_path),
        "has_photo": False,
        "photo_path": None,
        "text_bottom": y,
        "limit_bottom": H - 150,
        "overflow": not h_fit,
        "headline_size": h_size,
        "subtext_size": 32,
    }
