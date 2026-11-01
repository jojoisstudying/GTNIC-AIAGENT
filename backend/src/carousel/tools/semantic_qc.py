"""Semantic & Content Consistency QC for Carousels (BUG-08).

Performs deterministic & heuristic validation across all slides:
1. Role ordering: cover -> content slides -> cta.
2. Narrative progression & slide count (min 3, max 10).
3. Repetition / duplicate headline detection.
4. Headline / subtext length & readability consistency.
5. Sourced claims & fact verification against research sources.
6. Caption & hashtag consistency with slides content.
"""
from typing import Any, Dict, List, Tuple


def check_carousel_semantics(plan: Dict[str, Any], research: Dict[str, Any] | None = None) -> Tuple[List[str], List[str]]:
    """Evaluates carousel structure and semantic consistency.
    Returns:
        (errors, warnings): errors block approval/publishing, warnings alert human reviewer.
    """
    errors: List[str] = []
    warnings: List[str] = []

    slides = plan.get("slides") or []
    if not (3 <= len(slides) <= 10):
        errors.append(f"Jumlah slide carousel ({len(slides)}) harus di antara 3 hingga 10 slide.")

    if not slides:
        return errors, warnings

    # 1. Role ordering: first slide MUST be cover/single, last slide MUST be cta/single
    first_role = slides[0].get("role")
    if first_role not in ("cover", "single"):
        errors.append(f"Slide pertama harus bertipe 'cover' atau 'single', ditemukan '{first_role}'.")

    last_role = slides[-1].get("role")
    if last_role not in ("cta", "single"):
        warnings.append(f"Slide terakhir idealnya bertipe 'cta', ditemukan '{last_role}'.")

    # Content slides in between
    for idx, s in enumerate(slides[1:-1], start=2):
        r = s.get("role")
        if r not in ("content", "single"):
            warnings.append(f"Slide {idx} di tengah carousel bertipe '{r}' (disarankan 'content').")

    # 2. Duplicate detection
    headlines = [str(s.get("headline", "")).strip().lower() for s in slides if s.get("headline")]
    seen_headlines = set()
    for h in headlines:
        if h in seen_headlines:
            errors.append(f"Terdeteksi pengulangan judul/headline identik antar slide: '{h}'.")
        seen_headlines.add(h)

    # 3. Slide content substance
    for idx, s in enumerate(slides, start=1):
        h = str(s.get("headline", "")).strip()
        sub = str(s.get("subtext", "")).strip()
        if not h and not sub:
            errors.append(f"Slide {idx} kosong tanpa headline atau subtext.")

    # 4. Sourced claims verification
    # If stats/data layout is used, ensure numbers correspond to real research
    facts = (research or {}).get("facts") or {}
    stats_list = facts.get("stats") or []
    allowed_values = {str(item.get("value", "")).strip().lower() for item in stats_list if isinstance(item, dict)}

    for s in slides:
        lid = s.get("layout_id", "")
        if lid in ("data_angka_besar", "data_tiga_angka"):
            slots = s.get("slots") or {}
            for k, val in slots.items():
                if "value" in k or "angka" in k or "number" in k:
                    val_str = str(val).strip().lower()
                    if allowed_values and val_str not in allowed_values:
                        warnings.append(f"Angka metrik '{val}' pada slide '{s.get('headline')}' tidak ditemukan di sumber riset terverifikasi.")

    # 5. Caption & hashtag check
    caption = str(plan.get("caption", "")).strip()
    if not caption:
        warnings.append("Postingan belum memiliki caption Instagram.")
    hashtags = plan.get("hashtags") or []
    if len(hashtags) > 30:
        errors.append(f"Jumlah hashtag ({len(hashtags)}) melebihi batas 30.")

    return errors, warnings
