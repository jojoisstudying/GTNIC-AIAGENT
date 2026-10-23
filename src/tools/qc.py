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
    c, issues = brand["colors"], []
    if contrast_ratio(c["text_on_primary"], c["primary"]) < 4.5:
        issues.append("Kontras text_on_primary terhadap primary < 4.5")
    if contrast_ratio(c["secondary"], c["primary"]) < 4.5:
        issues.append("Kontras secondary terhadap primary < 4.5 (subtext sulit dibaca)")
    if contrast_ratio(c["accent"], c["primary"]) < 3:
        issues.append("Kontras accent terhadap primary < 3")
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