"""Ikon garis (viewBox 24x24) buatan sendiri + penanda UI. Tanpa dependensi eksternal."""
from __future__ import annotations

from markupsafe import Markup

ICON_PATHS: dict[str, str] = {
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
    "alert": '<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5"/><path d="M12 17.3v.1"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.2l3.4 2"/>',
    "shield": '<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8-7.5 9.5-4.3-1.5-7.5-4.9-7.5-9.5V6z"/><path d="M8.8 12l2.5 2.5 4-5"/>',
    "bulb": '<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
    "users": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/><circle cx="17.5" cy="9" r="2.5"/><path d="M17 14.2c2.6.2 4.5 2 4.5 4.8"/>',
    "doc": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6"/><path d="M9 16h6"/>',
    "chart": '<path d="M4 20V4"/><path d="M4 20h16"/><path d="M8 16v-4"/><path d="M12 16V8"/><path d="M16 16v-6"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
}
ICON_NAMES: tuple[str, ...] = tuple(ICON_PATHS)

MARK_PATHS: dict[str, str] = {
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "bookmark": '<path d="M6.5 3.5h11v17L12 16.5l-5.5 4z"/>',
    "arrow_down": '<path d="M12 4v15"/><path d="M6 13.5l6 6 6-6"/>',
}


def _svg(body: str, size: int, stroke: float) -> Markup:
    return Markup(f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="currentColor" '
                  f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round" '
                  f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">{body}</svg>')


def icon_svg(name: str, size: int = 120, stroke: float = 2) -> Markup:
    if name not in ICON_PATHS:
        raise KeyError(f"ikon tidak dikenal: {name!r}; pilihan: {ICON_NAMES}")
    return _svg(ICON_PATHS[name], size, stroke)


def mark_svg(name: str, size: int = 36, stroke: float = 2.6) -> Markup:
    if name not in MARK_PATHS:
        raise KeyError(f"penanda tidak dikenal: {name!r}")
    return _svg(MARK_PATHS[name], size, stroke)
