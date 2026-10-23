"""Utilitas warna kecil: parse hex, mix, luminance, kontras WCAG."""
from __future__ import annotations


def parse_hex(value: str) -> tuple[int, int, int]:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    if len(v) != 6:
        raise ValueError(f"Warna hex tidak valid: {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def to_hex(rgb: tuple[float, float, float]) -> str:
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def mix(a: str, b: str, t: float) -> str:
    """Campur a dan b. t=0 -> a, t=1 -> b."""
    ra, rb = parse_hex(a), parse_hex(b)
    return to_hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def rgba(value: str, alpha: float) -> str:
    r, g, b = parse_hex(value)
    return f"rgba({r},{g},{b},{alpha:.3f})"


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_lum(l1: float, l2: float) -> float:
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def contrast(a: str, b: str) -> float:
    return contrast_lum(luminance(parse_hex(a)), luminance(parse_hex(b)))


def best_text_on(bg: str, candidates: tuple[str, ...] = ("#0B1B3A", "#FFFFFF")) -> str:
    """Pilih warna teks dengan kontras tertinggi terhadap bg."""
    return max(candidates, key=lambda c: contrast(c, bg))
