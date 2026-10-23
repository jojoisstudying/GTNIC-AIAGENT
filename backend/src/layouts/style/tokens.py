"""Token warna turunan dari config/brand.json untuk dua permukaan: dark dan light.

Palet brand dikunci: hanya brand.tokens (atau brand.colors) yang jadi sumber.
"""
from __future__ import annotations

from .color import best_text_on, mix, rgba

SURFACES = ("dark", "light")


def base_colors(brand: dict) -> dict:
    t = brand.get("tokens") or {}
    c = brand.get("colors") or {}
    bg = t.get("bg") or c.get("primary")
    fg = t.get("fg") or c.get("text_on_primary") or "#FFFFFF"
    accent = t.get("accent") or c.get("accent")
    light_bg = t.get("light_bg") or c.get("secondary") or "#F4F7FF"
    if not (bg and accent):
        raise ValueError("brand.json harus punya tokens/colors dengan bg(primary) dan accent")
    return {"bg": bg, "fg": fg, "accent": accent, "light_bg": light_bg}


def resolve_tokens(brand: dict, surface: str = "dark") -> dict:
    if surface not in SURFACES:
        raise ValueError(f"surface harus salah satu dari {SURFACES}")
    b = base_colors(brand)
    if surface == "dark":
        bg, bg2, fg = b["bg"], mix(b["bg"], "#000000", 0.38), b["fg"]
        muted = fg
        ghost = rgba(fg, 0.17)
    else:
        bg, bg2, fg = b["light_bg"], mix(b["light_bg"], "#FFFFFF", 0.55), b["bg"]
        fg = mix(fg, "#000000", 0.25)
        muted = fg
        ghost = rgba(fg, 0.16)
    accent = b["accent"]
    return {
        "bg": bg, "bg2": bg2, "fg": fg, "muted": muted, "accent": accent,
        "accent_fg": best_text_on(accent), "ghost": ghost,
        "line": rgba(fg, 0.14), "fill_soft": rgba(fg, 0.07),
        "pattern": rgba(fg, 0.20), "pattern_soft": rgba(fg, 0.11),
        "accent_a": rgba(accent, 0.30), "bg_a85": rgba(bg, 0.88), "surface": surface,
    }
