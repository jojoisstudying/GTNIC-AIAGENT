"""Style pack: identitas visual satu carousel, deterministik dari seed, di dalam token brand.

Dekorasi digambar di ruang 'panorama' selebar total_slide*1080 sehingga bentuk yang
melewati batas slide tampak menyambung saat di-swipe.
"""
from __future__ import annotations

import math
import random
from html import escape

from .tokens import resolve_tokens

W, H = 1080, 1350
PATTERNS = ("grid_halus", "titik", "glow_radial", "diagonal", "polos_noise", "garis_kontur")
SHAPES = ("circle", "ring", "half", "block", "bars", "plus")
TEXTURES = ("none", "grain")


def build_pack(seed: int, brand: dict, total: int = 5, force_surface: str | None = None) -> dict:
    """Bangun style pack. Hasil murni dict (bisa disimpan di plan/DB)."""
    rng = random.Random(seed)
    surface = force_surface or ("light" if rng.random() < 0.25 else "dark")
    tokens = resolve_tokens(brand, surface)
    pattern = rng.choice(PATTERNS)
    texture = rng.choice(TEXTURES)
    emphasis_style = "marker" if surface == "light" else rng.choice(("color", "marker"))
    if pattern == "glow_radial":   # teks beraksen di atas glow beraksen: kontras tak terjamin -> pakai kotak (latar sendiri)
        emphasis_style = "marker"
    pano_w = W * max(1, total)

    shapes: list[dict] = []
    n = rng.randint(3, 5)
    boundaries = [k * W for k in range(1, max(1, total))]
    for i in range(n):
        shape = rng.choice(SHAPES)
        size = rng.randint(220, 640)
        if i == 0 and boundaries:  # satu bentuk wajib menyeberang batas slide
            cx = rng.choice(boundaries) + rng.randint(-70, 70)
        else:
            cx = rng.randint(0, pano_w)
        cy = rng.randint(-80, H + 80)
        tone = rng.choice(("fg", "fg", "bg2", "accent"))
        if tone == "accent" and any(s["tone"] == "accent" for s in shapes):
            tone = "fg"  # aksen hemat: maksimal satu bentuk beraksen
        opacity = round(rng.uniform(0.30, 0.45), 2) if tone == "accent" else round(rng.uniform(0.05, 0.11), 3)
        if tone == "accent":
            size = min(size, 300)
        shapes.append({"shape": shape, "cx": cx, "cy": cy, "size": size,
                       "rotate": rng.choice((0, 15, 30, 45, -15, -30)), "tone": tone, "opacity": opacity})

    return {
        "pack_id": f"{pattern}-{seed % 1000:03d}",
        "seed": seed,
        "surface": surface,
        "pattern": pattern,
        "texture": texture,
        "emphasis_style": emphasis_style,
        "bg_angle": rng.choice((180, 165, 200, 150)),
        "glow": {"cx": rng.randint(0, pano_w), "cy": rng.randint(150, 700),
                 "r": rng.randint(520, 900), "alpha": round(rng.uniform(0.10, 0.20), 3)},
        "waves": [round(rng.uniform(0.6, 1.4), 2) for _ in range(4)],
        "shapes": shapes,
        "tokens": tokens,
        "total": total,
    }


# ---------- Render ke HTML/SVG ----------

_GRAIN = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'>"
          "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/>"
          "<feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.55 0'/></filter>"
          "<rect width='100%' height='100%' filter='url(%23n)'/></svg>")


def bg_html(pack: dict, index: int) -> str:
    t = pack["tokens"]
    layers: list[str] = []
    px = index * W
    pat = pack["pattern"]
    if pat == "grid_halus":
        c = t["line"]   # grid sengaja tidak diterangkan: garis tipis di belakang teks menurunkan kontras terukur
        layers.append(f"linear-gradient({c} 1px, transparent 1px) 0 0/60px 60px")
        layers.append(f"linear-gradient(90deg,{c} 1px, transparent 1px) 0 0/60px 60px")
    elif pat == "titik":
        layers.append(f"radial-gradient({t['pattern']} 2.5px, transparent 3px) 0 0/36px 36px")
    elif pat == "diagonal":
        layers.append(f"repeating-linear-gradient(135deg, transparent 0 34px, {t['pattern_soft']} 34px 37px)")
    g = pack["glow"]
    gx = g["cx"] - px
    glow_alpha = g["alpha"] * 1.6 if pat == "glow_radial" else g["alpha"] * 0.7
    layers.append(f"radial-gradient(circle {g['r']}px at {gx}px {g['cy']}px, "
                  f"rgba(255,255,255,{glow_alpha:.3f}), transparent 70%)")
    layers.append(f"linear-gradient({pack['bg_angle']}deg, {t['bg']}, {t['bg2']})")
    style = f"position:absolute;inset:0;background:{','.join(layers)};"
    extra = ""
    if pat == "garis_kontur":
        extra = _waves_svg(pack, index)
    grain = ""
    if pack["texture"] == "grain" or pat == "polos_noise":
        op = 0.10 if pat == "polos_noise" else 0.07
        grain = (f"<div style=\"position:absolute;inset:0;opacity:{op};mix-blend-mode:overlay;"
                 f"background:url(&quot;{_GRAIN}&quot;)\"></div>")
    return f'<div style="{style}"></div>{extra}{grain}'


def _waves_svg(pack: dict, index: int) -> str:
    t = pack["tokens"]
    pano = W * pack["total"]
    paths = []
    for k, amp in enumerate(pack["waves"]):
        y0 = 260 + k * 250
        pts = []
        for x in range(0, pano + 1, 40):
            y = y0 + math.sin(x / (210 + 60 * amp) + k) * (46 * amp + 18)
            pts.append(f"{x},{y:.1f}")
        paths.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{t["pattern"]}" stroke-width="3"/>')
    return (f'<svg style="position:absolute;inset:0" width="{W}" height="{H}" viewBox="{index * W} 0 {W} {H}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(paths)}</svg>')


def _accent_outline(kind: str, x: float, y: float, r: float, rot: int, color: str) -> str:
    """Bentuk beraksen digambar sebagai garis tegas (bukan isian transparan yang tampak keruh)."""
    common = (f'fill="none" stroke="{color}" stroke-width="5" stroke-linejoin="round" '
              f'stroke-linecap="round" opacity="0.55"')
    g = f'transform="rotate({rot} {x} {y})"'
    if kind in ("circle", "ring"):
        return f'<circle cx="{x}" cy="{y}" r="{r}" {common}/>'
    if kind == "half":
        return f'<path {g} d="M{x - r},{y} A{r},{r} 0 0 1 {x + r},{y} Z" {common}/>'
    if kind == "block":
        return f'<rect {g} x="{x - r}" y="{y - r * 0.55}" width="{2 * r}" height="{r * 1.1}" rx="{r * 0.12}" {common}/>'
    if kind == "bars":
        lines = "".join(f'<line x1="{x - r}" x2="{x + r}" y1="{y - r + i * r * 0.5}" y2="{y - r + i * r * 0.5}"/>' for i in range(4))
        return f'<g {g} {common}>{lines}</g>'
    a, b = r * 0.16, r      # plus: kontur salib
    pts = [(-a, -b), (a, -b), (a, -a), (b, -a), (b, a), (a, a), (a, b), (-a, b), (-a, a), (-b, a), (-b, -a), (-a, -a)]
    d = "M" + " L".join(f"{x + px:.1f},{y + py:.1f}" for px, py in pts) + " Z"
    return f'<path {g} d="{d}" {common}/>'


def _soft(color: str, op: float) -> str:
    """Isian tipis (tidak menerangkan area di belakang teks) + garis tepi tipis agar bentuk tetap terbaca."""
    return (f'fill="{color}" fill-opacity="{op}" stroke="{color}" stroke-opacity="{min(0.30, op * 2.6):.3f}" '
            f'stroke-width="3" stroke-linejoin="round"')


def _shape_svg(s: dict, tokens: dict) -> str:
    if s["tone"] == "accent":
        return _accent_outline(s["shape"], s["cx"], s["cy"], s["size"] / 2, s["rotate"], tokens["accent"])
    color = {"fg": tokens["fg"], "bg2": tokens["bg2"]}[s["tone"]]
    x, y, r = s["cx"], s["cy"], s["size"] / 2
    op, rot = s["opacity"], s["rotate"]
    tf = f'transform="rotate({rot} {x} {y})"'
    kind = s["shape"]
    if kind == "circle":
        return f'<circle cx="{x}" cy="{y}" r="{r}" {_soft(color, op)}/>'
    if kind == "ring":
        return f'<circle cx="{x}" cy="{y}" r="{r}" fill="none" stroke="{color}" stroke-width="{max(10, r * 0.12):.0f}" opacity="{op * 1.6:.3f}"/>'
    if kind == "half":
        return f'<path {tf} d="M{x - r},{y} A{r},{r} 0 0 1 {x + r},{y} Z" {_soft(color, op)}/>'
    if kind == "block":
        return f'<rect {tf} x="{x - r}" y="{y - r * 0.55}" width="{2 * r}" height="{r * 1.1}" rx="{r * 0.12}" {_soft(color, op)}/>'
    if kind == "bars":
        bars = "".join(f'<rect x="{x - r}" y="{y - r + i * r * 0.5}" width="{2 * r}" height="{r * 0.18}"/>' for i in range(4))
        return f'<g {tf} fill="{color}" fill-opacity="{min(0.2, op * 1.5):.3f}">{bars}</g>'
    t = r * 0.32      # plus
    return (f'<g {tf} fill="{color}" fill-opacity="{op}"><rect x="{x - r}" y="{y - t / 2}" width="{2 * r}" height="{t}"/>'
            f'<rect x="{x - t / 2}" y="{y - r}" width="{t}" height="{2 * r}"/></g>')


def deco_html(pack: dict, index: int) -> str:
    body = "".join(_shape_svg(s, pack["tokens"]) for s in pack["shapes"])
    return (f'<svg style="position:absolute;inset:0" width="{W}" height="{H}" viewBox="{index * W} 0 {W} {H}" '
            f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">{body}</svg>')


def css_vars(pack: dict) -> str:
    t = pack["tokens"]
    names = {"bg": "--bg", "bg2": "--bg2", "fg": "--fg", "muted": "--muted", "accent": "--accent",
             "accent_fg": "--accent-fg", "ghost": "--ghost", "line": "--line", "fill_soft": "--fill-soft",
             "accent_a": "--accent-a", "bg_a85": "--bg-a85"}
    return ";".join(f"{css}:{escape(t[k])}" for k, css in names.items())
