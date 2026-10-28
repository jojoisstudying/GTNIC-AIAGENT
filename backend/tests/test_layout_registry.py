"""Registry layout: muat, tolak layout rusak, katalog tanpa HTML, validasi konten."""
import json
import shutil
from pathlib import Path

import pytest

from src.carousel.layouts import registry
from src.carousel.layouts.models import LayoutError, validate_content

LID = "cover_judul_raksasa"
SRC = registry.LAYOUTS_DIR / LID


def _copy_root(tmp_path: Path) -> Path:
    shutil.copytree(SRC, tmp_path / LID)
    return tmp_path


def test_loads_layout_and_all_samples_are_valid() -> None:
    spec = registry.get(LID)
    assert spec.meta.role == "cover"
    for name, sample in spec.samples.items():
        errors = validate_content(spec, sample["slots"], sample.get("params"), sample.get("emphasis"))
        assert errors == [], (name, errors)


def test_catalog_only_exposes_approved_and_has_no_markup(tmp_path: Path) -> None:
    root = _copy_root(tmp_path)
    assert [item["id"] for item in registry.catalog(root)] == ["cover_judul_raksasa"]
    registry.set_status(LID, "approved", root)
    cat = registry.catalog(root)
    assert [c["id"] for c in cat] == [LID]
    assert "<" not in json.dumps(cat)
    assert cat[0]["slots"]["title"]["max_chars"] == 48


def test_rejects_invalid_meta_and_missing_files(tmp_path: Path) -> None:
    root = _copy_root(tmp_path)
    meta = root / LID / "meta.json"
    raw = json.loads(meta.read_text(encoding="utf-8"))
    raw["role"] = "tidak_ada"
    meta.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(LayoutError):
        registry.load_all(root)
    raw["role"] = "cover"
    meta.write_text(json.dumps(raw), encoding="utf-8")
    (root / LID / "schema.json").unlink()
    with pytest.raises(LayoutError):
        registry.load_all(root)


def test_validate_content_catches_violations() -> None:
    spec = registry.get(LID)
    errs = validate_content(spec, {"title": "x" * 60, "bogus": "a"}, {"pos": "kiri"}, ["tidak ada"])
    joined = " | ".join(errs)
    assert "60 karakter" in joined
    assert "bogus" in joined
    assert "pos" in joined
    assert "emphasis" in joined
    assert validate_content(spec, {}, {}, []) == ["slot wajib 'title' kosong"]


def test_status_roundtrip(tmp_path: Path) -> None:
    root = _copy_root(tmp_path)
    registry.set_status(LID, "approved", root)
    assert registry.get(LID, root).meta.status == "approved"
    registry.set_status(LID, "retired", root)
    assert registry.get(LID, root).meta.status == "retired"
    with pytest.raises(LayoutError):
        registry.set_status(LID, "bebas", root)
