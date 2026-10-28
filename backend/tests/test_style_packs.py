"""Style pack: deterministik, bervariasi, menyambung antar slide, tetap di dalam palet brand."""
import json
from pathlib import Path

from src.carousel.layouts.style.color import contrast
from src.carousel.layouts.style.packs import W, build_pack
from src.carousel.layouts.style.tokens import resolve_tokens

BRAND = json.loads((Path(__file__).resolve().parents[1] / "config" / "brand.json").read_text(encoding="utf-8"))


def test_same_seed_same_pack() -> None:
    assert build_pack(7, BRAND) == build_pack(7, BRAND)


def test_different_seeds_differ() -> None:
    packs = [build_pack(s, BRAND) for s in range(30)]
    assert len({p["pack_id"] for p in packs}) > 10
    assert len({json.dumps(p["shapes"]) for p in packs}) == 30


def test_a_shape_crosses_a_slide_boundary() -> None:
    boundaries = [k * W for k in range(1, 5)]
    for seed in range(50):
        shapes = build_pack(seed, BRAND, total=5)["shapes"]
        assert any(abs(s["cx"] - b) <= 70 for s in shapes for b in boundaries), seed


def test_at_most_one_accent_shape_and_both_surfaces_appear() -> None:
    surfaces = set()
    for seed in range(100):
        pack = build_pack(seed, BRAND)
        assert sum(s["tone"] == "accent" for s in pack["shapes"]) <= 1
        surfaces.add(pack["surface"])
    assert surfaces == {"dark", "light"}


def test_text_tokens_are_readable_on_both_surfaces() -> None:
    for surface in ("dark", "light"):
        t = resolve_tokens(BRAND, surface)
        assert contrast(t["fg"], t["bg"]) >= 7
        assert contrast(t["muted"], t["bg"]) >= 4.5
        assert contrast(t["accent_fg"], t["accent"]) >= 4.5
