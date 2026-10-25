"""Subtitle and Kinetic Typography Overlay Builder using Pillow and MoviePy."""

import os
import json
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

from src import config
from src.video.models import WordTiming

FONT_PATH_DEFAULT = config.ROOT / "src" / "render" / "fonts" / "Poppins-Bold.ttf"
BRAND_JSON_PATH = config.ROOT / "config" / "brand.json"

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

# Safe zone constants for Instagram Reels (vertical 9:16)
SAFE_TOP = 250       # Avoid IG header icons
SAFE_BOTTOM = 1550   # Avoid IG bottom caption & audio title
SUBTITLE_Y = 1200    # Optimal focal area for animated subtitles
HEADLINE_Y = 320     # Optimal area for scene headline overlay


def load_brand_tokens() -> dict:
    """Load colors and tokens from brand.json."""
    if BRAND_JSON_PATH.exists():
        try:
            with open(BRAND_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("tokens", {})
        except Exception:
            pass
    return {
        "bg": "#0B2A5B",
        "fg": "#FFFFFF",
        "accent": "#FFB400",
        "accent_fg": "#0B1B3A",
    }


def hex_to_rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    """Convert hex string (e.g. #FFB400) to RGBA tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (r, g, b, alpha)
    return (255, 255, 255, alpha)


def get_font(size: int = 48, font_path: Optional[Path] = None) -> ImageFont.FreeTypeFont:
    path = font_path or FONT_PATH_DEFAULT
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()  # type: ignore


def group_words_into_phrases(
    words: List[WordTiming], max_words: int = 4
) -> List[Tuple[int, int, List[WordTiming]]]:
    """
    Group stream of words into readable short phrases for reels (2-4 words per card).
    Ensures seamless contiguous timestamps between words to eliminate highlight flickering.
    Returns list of (start_ms, end_ms, [WordTiming]).
    """
    if not words:
        return []

    # 1. Seamless gap-filling: make each word extend cleanly to the start of next word
    seamless_words: List[WordTiming] = []
    for i in range(len(words)):
        w = words[i]
        curr_start = w.start_ms
        if i < len(words) - 1:
            next_start = words[i + 1].start_ms
            curr_end = max(w.end_ms, next_start)
        else:
            curr_end = max(w.end_ms, curr_start + 400)
        seamless_words.append(WordTiming(word=w.word, start_ms=curr_start, end_ms=curr_end))

    phrases = []
    current_chunk: List[WordTiming] = []

    for w in seamless_words:
        current_chunk.append(w)
        if len(current_chunk) >= max_words or w.word.endswith((".", "!", "?", ",")):
            start_ms = current_chunk[0].start_ms
            end_ms = current_chunk[-1].end_ms
            phrases.append((start_ms, end_ms, list(current_chunk)))
            current_chunk = []

    if current_chunk:
        start_ms = current_chunk[0].start_ms
        end_ms = current_chunk[-1].end_ms
        phrases.append((start_ms, end_ms, list(current_chunk)))

    return phrases


def create_kinetic_subtitle_frame(
    phrase_words: List[WordTiming],
    active_word_index: int,
    canvas_w: int = CANVAS_WIDTH,
    canvas_h: int = CANVAS_HEIGHT,
    font_size: int = 54,
) -> np.ndarray:
    """
    Render a single transparent frame with kinetic typography:
    - Inactive words: white with subtle shadow
    - Active word (spoken right now): brand accent background badge or highlight color
    """
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    tokens = load_brand_tokens()

    font = get_font(size=font_size)
    space_w = font.getbbox(" ")[2] - font.getbbox(" ")[0] if hasattr(font, "getbbox") else 20

    # Calculate word bboxes
    word_boxes = []
    total_w = 0
    max_h = 0

    for idx, wt in enumerate(phrase_words):
        bbox = draw.textbbox((0, 0), wt.word, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        word_boxes.append((w, h))
        total_w += w + (space_w if idx < len(phrase_words) - 1 else 0)
        max_h = max(max_h, h)

    # Center horizontally around SUBTITLE_Y
    start_x = (canvas_w - total_w) // 2
    cur_x = start_x
    y = SUBTITLE_Y

    # Draw semi-transparent background capsule for overall phrase readability
    padding_x = 28
    padding_y = 16
    pill_box = [
        start_x - padding_x,
        y - padding_y,
        start_x + total_w + padding_x,
        y + max_h + padding_y + 8,
    ]
    draw.rounded_rectangle(pill_box, radius=18, fill=(11, 27, 58, 200))  # Brand navy translucent

    # Draw individual words
    accent_color = hex_to_rgba(tokens.get("accent", "#FFB400"))
    text_color = hex_to_rgba(tokens.get("fg", "#FFFFFF"))
    accent_fg = hex_to_rgba(tokens.get("accent_fg", "#0B1B3A"))

    for idx, (wt, (w, h)) in enumerate(zip(phrase_words, word_boxes)):
        is_active = idx == active_word_index

        if is_active:
            # Active word gets an animated bright badge
            badge_pad_x = 10
            badge_pad_y = 6
            badge_rect = [
                cur_x - badge_pad_x,
                y - badge_pad_y,
                cur_x + w + badge_pad_x,
                y + h + badge_pad_y + 6,
            ]
            draw.rounded_rectangle(badge_rect, radius=8, fill=accent_color)
            draw.text((cur_x, y), wt.word, font=font, fill=accent_fg)
        else:
            draw.text((cur_x, y), wt.word, font=font, fill=text_color)

        cur_x += w + space_w

    return np.array(img)


def create_headline_overlay_frame(
    headline: str,
    canvas_w: int = CANVAS_WIDTH,
    canvas_h: int = CANVAS_HEIGHT,
    font_size: int = 64,
) -> np.ndarray:
    """
    Render a punchy corporate headline card in the top safe area (HEADLINE_Y).
    """
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    if not headline:
        return np.array(img)

    draw = ImageDraw.Draw(img)
    tokens = load_brand_tokens()
    font = get_font(size=font_size)

    clean_headline = headline.upper().strip()
    bbox = draw.textbbox((0, 0), clean_headline, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Center card horizontally at HEADLINE_Y
    card_x = (canvas_w - text_w) // 2
    card_y = HEADLINE_Y

    pad_x = 36
    pad_y = 20
    rect = [
        card_x - pad_x,
        card_y - pad_y,
        card_x + text_w + pad_x,
        card_y + text_h + pad_y + 8,
    ]

    accent_color = hex_to_rgba(tokens.get("accent", "#FFB400"))
    accent_fg = hex_to_rgba(tokens.get("accent_fg", "#0B1B3A"))

    # Glowing border + card background
    draw.rounded_rectangle(rect, radius=16, fill=accent_color)
    draw.text((card_x, card_y), clean_headline, font=font, fill=accent_fg)

    return np.array(img)


def create_branded_outro_frame(
    brand_config: Optional[Dict[str, Any]] = None,
    canvas_w: int = CANVAS_WIDTH,
    canvas_h: int = CANVAS_HEIGHT,
) -> np.ndarray:
    """
    Render a polished corporate Outro Card showing company name, industry, logo/badge,
    contact info, and handle from brand.json.
    """
    img = Image.new("RGBA", (canvas_w, canvas_h), (11, 42, 91, 255))  # Brand navy primary
    draw = ImageDraw.Draw(img)

    brand_file = config.ROOT / "config" / "brand.json"
    brand_data = brand_config or {}
    if not brand_data and brand_file.exists():
        try:
            with open(brand_file, "r", encoding="utf-8") as f:
                brand_data = json.load(f)
        except Exception:
            pass

    company_name = brand_data.get("company", "GTNIC ENTERPRISE").upper()
    industry = brand_data.get("industry", "Solusi Otomasi Industri").title()
    colors = brand_data.get("colors", {})
    accent_hex = colors.get("accent", "#FFB400")
    accent_color = hex_to_rgba(accent_hex)
    text_color = (255, 255, 255, 255)

    font_display = get_font(size=72)
    font_sub = get_font(size=38)
    font_body = get_font(size=44)

    # 1. Subtle decorative background shapes
    draw.ellipse([-100, -100, 600, 600], fill=(18, 56, 118, 120))
    draw.ellipse([canvas_w - 500, canvas_h - 500, canvas_w + 200, canvas_h + 200], fill=(18, 56, 118, 120))

    # 2. Brand Icon / Badge (Circular Emblem)
    badge_cx = canvas_w // 2
    badge_cy = 600
    badge_radius = 110
    draw.ellipse(
        [badge_cx - badge_radius, badge_cy - badge_radius, badge_cx + badge_radius, badge_cy + badge_radius],
        fill=accent_color,
    )
    # Inner emblem letter
    first_letter = company_name[0] if company_name else "G"
    font_badge = get_font(size=110)
    b_box = draw.textbbox((0, 0), first_letter, font=font_badge)
    bw, bh = b_box[2] - b_box[0], b_box[3] - b_box[1]
    draw.text((badge_cx - bw // 2, badge_cy - bh // 2 - 10), first_letter, font=font_badge, fill=(11, 27, 58, 255))

    # 3. Company Name
    c_box = draw.textbbox((0, 0), company_name, font=font_display)
    cw = c_box[2] - c_box[0]
    draw.text(((canvas_w - cw) // 2, 800), company_name, font=font_display, fill=text_color)

    # 4. Industry Subtitle
    ind_clean = f"• {industry} •"
    i_box = draw.textbbox((0, 0), ind_clean, font=font_sub)
    iw = i_box[2] - i_box[0]
    draw.text(((canvas_w - iw) // 2, 890), ind_clean, font=font_sub, fill=accent_color)

    # 5. Divider Line
    draw.line([(canvas_w // 2) - 180, 970, (canvas_w // 2) + 180, 970], fill=accent_color, width=4)

    # 6. Contact & Footer Lines
    footer_cfg = brand_data.get("chrome", {}).get("footer", {})
    footer_lines = footer_cfg.get("lines", ["@gtnic_official", "0812-3456-7890"])

    contact_y = 1040
    for line in footer_lines:
        line_clean = str(line).strip()
        pill_box_w = 640
        pill_box_h = 80
        px1 = (canvas_w - pill_box_w) // 2
        px2 = px1 + pill_box_w
        py1 = contact_y
        py2 = py1 + pill_box_h

        draw.rounded_rectangle([px1, py1, px2, py2], radius=20, fill=(18, 56, 118, 220), outline=accent_color, width=2)
        
        t_box = draw.textbbox((0, 0), line_clean, font=font_body)
        tw, th = t_box[2] - t_box[0], t_box[3] - t_box[1]
        draw.text(((canvas_w - tw) // 2, py1 + (pill_box_h - th) // 2 - 4), line_clean, font=font_body, fill=text_color)

        contact_y += 110

    # 7. CTA Bottom Tag
    cta_tag = "SAVE & SHARE VIDEO INI"
    font_cta = get_font(size=36)
    tag_box = draw.textbbox((0, 0), cta_tag, font=font_cta)
    tag_w = tag_box[2] - tag_box[0]
    draw.text(((canvas_w - tag_w) // 2, 1380), cta_tag, font=font_cta, fill=accent_color)

    return np.array(img)

