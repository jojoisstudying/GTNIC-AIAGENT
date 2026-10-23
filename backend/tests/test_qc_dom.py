"""QC lapis 1 dari laporan DOM sintetis."""
from src.tools import qc_dom


def item(id="title#1", x=64, y=300, w=900, h=120, **kw) -> dict:
    base = {"id": id, "slot": "title", "kind": "text", "bbox": {"x": x, "y": y, "w": w, "h": h},
            "font_px": 100, "min_font": 72, "fits": True, "bleed": False, "contrast_min": 9.0}
    base.update(kw)
    return base


def codes(report: list[dict]) -> set[str]:
    return {i.code for i in qc_dom.evaluate(report) if i.severity == "error"}


def test_clean_report_passes() -> None:
    assert qc_dom.passed(qc_dom.evaluate([item(h=800)]))


def test_detects_each_failure_mode() -> None:
    assert "overflow" in codes([item(fits=False)])
    assert "font_terlalu_kecil" in codes([item(font_px=40)])
    assert "kontras_rendah" in codes([item(contrast_min=2.0)])
    assert "margin_aman" in codes([item(x=10)])
    assert "menabrak_header" in codes([item(y=90)])
    assert "menabrak_footer" in codes([item(y=1150, h=100)])
    assert "keluar_kanvas" in codes([item(x=900, w=400, bleed=False, slot=None)])
    assert "tumpang_tindih" in codes([item(id="a"), item(id="b", y=320)])


def test_large_text_has_relaxed_contrast_and_bleed_is_exempt() -> None:
    assert "kontras_rendah" not in codes([item(contrast_min=3.2, font_px=100)])
    assert "kontras_rendah" in codes([item(contrast_min=3.2, font_px=30, min_font=0)])
    assert codes([item(x=-200, w=1500, bleed=True)]) == set()
