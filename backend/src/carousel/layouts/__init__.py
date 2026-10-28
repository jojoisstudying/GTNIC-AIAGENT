"""Public API for the legacy image layouts and carousel rhythm checks.

The data-driven HTML layouts are exposed separately as ``src.carousel.layouts.registry``.
"""

from . import (
	angka_besar,
	cta_blok,
	daftar_bernomor,
	foto_penuh_overlay,
	kutipan,
	langkah_diagram,
	perbandingan,
	split_foto_teks,
	tipografi_minimal,
)

LAYOUT_REGISTRY = {
	module.LAYOUT_ID: module.render
	for module in (
		angka_besar,
		split_foto_teks,
		foto_penuh_overlay,
		kutipan,
		daftar_bernomor,
		perbandingan,
		tipografi_minimal,
		langkah_diagram,
		cta_blok,
	)
}
VALID_LAYOUT_IDS = tuple(LAYOUT_REGISTRY)


def get_layout_renderer(layout_id: str):
	"""Return the renderer registered for ``layout_id``."""
	try:
		return LAYOUT_REGISTRY[layout_id]
	except KeyError as exc:
		raise ValueError(
			f"Layout '{layout_id}' tidak dikenal; pilihan: {VALID_LAYOUT_IDS}"
		) from exc


def validate_rhythm(slides: list[dict]) -> list[str]:
	"""Validate visual variation rules for a carousel."""
	issues = []
	layout_ids = [slide.get("layout_id") for slide in slides]

	for index in range(1, len(layout_ids)):
		if layout_ids[index] == layout_ids[index - 1]:
			issues.append(
				f"slide {index + 1}: layout '{layout_ids[index]}' berulang berurutan"
			)

	if slides:
		cover_layout = next(
			(slide.get("layout_id") for slide in slides if slide.get("role") == "cover"),
			None,
		)
		if cover_layout is not None and any(
			slide.get("role") == "content" and slide.get("layout_id") == cover_layout
			for slide in slides
		):
			issues.append("cover memakai layout yang sama dengan slide isi")

	distinct_layouts = {layout_id for layout_id in layout_ids if layout_id is not None}
	if len(distinct_layouts) < 3:
		issues.append("carousel harus memakai minimal 3 layout berbeda")

	return issues


__all__ = [
	"LAYOUT_REGISTRY",
	"VALID_LAYOUT_IDS",
	"get_layout_renderer",
	"validate_rhythm",
]
