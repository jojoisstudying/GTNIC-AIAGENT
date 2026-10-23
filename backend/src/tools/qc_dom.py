"""QC lapis 1: periksa laporan DOM hasil renderer. Deterministik, tanpa LLM."""
from __future__ import annotations

from dataclasses import dataclass

CANVAS_W, CANVAS_H = 1080, 1350
MARGIN = 64
TOL = 2
HEADER_BOTTOM = 150      # konten tidak boleh masuk zona header chrome
FOOTER_TOP = 1215        # ...atau zona footer chrome
LARGE_TEXT_PX = 48
MIN_CONTRAST, MIN_CONTRAST_LARGE = 4.5, 3.0
MIN_FILL = 0.28          # peringatan kalau konten terlalu sedikit memenuhi area aman


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str  # "error" | "warn"
    element: str
    detail: str


def _inter(a: dict, b: dict) -> tuple[float, float]:
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return w, h


def evaluate(report: list[dict]) -> list[Issue]:
    issues: list[Issue] = []
    content = [i for i in report if i["kind"] == "text" and i.get("slot")]
    for it in report:
        eid, b = it["id"], it["bbox"]
        if not it["fits"]:
            issues.append(Issue("overflow", "error", eid, "teks tidak muat di kotaknya"))
        if it["min_font"] and it["font_px"] < it["min_font"] - 0.5:
            issues.append(Issue("font_terlalu_kecil", "error", eid,
                                f"{it['font_px']:.0f}px < minimum {it['min_font']}px"))
        c = it.get("contrast_min")
        if c is not None:
            need = MIN_CONTRAST_LARGE if it["font_px"] >= LARGE_TEXT_PX else MIN_CONTRAST
            if c < need:
                issues.append(Issue("kontras_rendah", "error", eid, f"kontras {c:.1f}:1 < {need}:1"))
        if it["bleed"]:
            continue
        out = (b["x"] < -TOL or b["y"] < -TOL or b["x"] + b["w"] > CANVAS_W + TOL or b["y"] + b["h"] > CANVAS_H + TOL)
        if out:
            issues.append(Issue("keluar_kanvas", "error", eid, "elemen melewati tepi kanvas tanpa data-bleed"))
    for it in content:
        b, eid = it["bbox"], it["id"]
        if it["bleed"]:
            continue
        if b["x"] < MARGIN - TOL or b["x"] + b["w"] > CANVAS_W - MARGIN + TOL:
            issues.append(Issue("margin_aman", "error", eid, f"x={b['x']:.0f}..{b['x'] + b['w']:.0f} di luar margin {MARGIN}px"))
        if b["y"] < HEADER_BOTTOM - TOL:
            issues.append(Issue("menabrak_header", "error", eid, f"y={b['y']:.0f} masuk zona header"))
        if b["y"] + b["h"] > FOOTER_TOP + TOL:
            issues.append(Issue("menabrak_footer", "error", eid, f"bawah={b['y'] + b['h']:.0f} masuk zona footer"))
    for i, a in enumerate(content):
        for b in content[i + 1:]:
            w, h = _inter(a["bbox"], b["bbox"])
            if w > 6 and h > 6:
                issues.append(Issue("tumpang_tindih", "error", f"{a['id']}~{b['id']}", f"irisan {w:.0f}x{h:.0f}px"))
    if content:
        x0 = min(i["bbox"]["x"] for i in content)
        x1 = max(i["bbox"]["x"] + i["bbox"]["w"] for i in content)
        y0 = min(i["bbox"]["y"] for i in content)
        y1 = max(i["bbox"]["y"] + i["bbox"]["h"] for i in content)
        zone = (CANVAS_W - 2 * MARGIN) * (FOOTER_TOP - HEADER_BOTTOM)
        fill = max(0, (x1 - x0)) * max(0, (y1 - y0)) / zone
        if fill < MIN_FILL:
            issues.append(Issue("konten_terlalu_sedikit", "warn", "-", f"konten hanya {fill:.0%} area aman"))
    return issues


def passed(issues: list[Issue]) -> bool:
    return not any(i.severity == "error" for i in issues)
