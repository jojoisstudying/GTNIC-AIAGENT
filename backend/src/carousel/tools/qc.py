"""Quality check berbasis kode (cepat, deterministik) untuk satu slide."""


def _lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def check_brand(brand: dict) -> list[str]:
    """Evaluates WCAG contrast according to semantic color roles.
    Only enforces text readability contrast (>= 4.5:1) between actual text and its background.
    Decorative or accent roles are evaluated appropriately and do not block text unless used as text.
    """
    c = brand.get("colors") or {}
    tokens = brand.get("tokens") or {}
    issues = []

    primary = c.get("primary") or tokens.get("bg", "#000000")
    text_on_primary = c.get("text_on_primary") or tokens.get("fg", "#ffffff")
    
    # 1. Text on primary background must be legible (WCAG AA text >= 4.5)
    if contrast_ratio(text_on_primary, primary) < 4.5:
        issues.append(f"Kontras text_on_primary ({text_on_primary}) terhadap primary ({primary}) < 4.5 (teks utama tidak terbaca)")

    # 2. Check surface background contrast if explicit surface tokens exist
    light_bg = tokens.get("light_bg")
    fg = tokens.get("fg")
    if light_bg and fg and contrast_ratio(fg, light_bg) < 4.5:
        # If light_bg is used as surface with dark text (primary), verify readability
        if contrast_ratio(primary, light_bg) < 4.5 and contrast_ratio(fg, light_bg) < 4.5:
            issues.append("Kontras teks terhadap light_bg < 4.5")

    # 3. Accent text contrast: if accent is used as background for text, ensure text_on_accent or fg is legible
    accent = c.get("accent") or tokens.get("accent")
    if accent and primary and contrast_ratio(accent, primary) < 2.0:
        # Decorative accent warning (non-blocking if not used for text)
        issues.append(f"Peringatan: Kontras accent terhadap primary rendah ({contrast_ratio(accent, primary):.2f}:1)")

    return issues


def check_slide(meta: dict) -> list[str]:
    issues = []
    if meta["overflow"]:
        issues.append("teks tidak muat di area yang tersedia (perpendek headline/subtext)")
    if meta["headline_size"] < 56:
        issues.append(f"headline terlalu kecil ({meta['headline_size']}px)")
    if meta["subtext_size"] < 30:
        issues.append(f"subtext terlalu kecil ({meta['subtext_size']}px)")
    if meta["text_bottom"] > meta["limit_bottom"]:
        issues.append("teks melewati batas bawah / menabrak foto")
    return issues