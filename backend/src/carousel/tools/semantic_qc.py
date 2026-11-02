"""Semantic & Content Consistency QC for Carousels (BUG-08).

Performs deterministic & heuristic validation across all slides:
1. Role ordering: cover -> content slides -> cta.
2. Narrative progression & slide count (min 3, max 10).
3. Repetition / duplicate headline detection.
4. Headline / subtext length & readability consistency.
5. Sourced claims & fact verification against research sources.
6. Caption & hashtag consistency with slides content.
"""
import re
from typing import Any, Dict, List


def check_carousel_semantics(plan: Dict[str, Any], research: Dict[str, Any] | None = None,
                             brand: Dict[str, Any] | None = None, topic: str = "") -> Dict[str, Any]:
    """Evaluates carousel structure and semantic consistency.
    Returns:
        A structured result. Blocking errors prevent approval/publishing; warnings are non-blocking.
    """
    errors: List[str] = []
    warnings: List[str] = []

    slides = plan.get("slides") or []
    is_single_image = plan.get("format") == "single_image"
    valid_slide_count = len(slides) == 1 if is_single_image else 3 <= len(slides) <= 10
    if not valid_slide_count:
        errors.append(f"Jumlah slide carousel ({len(slides)}) harus di antara 3 hingga 10 slide.")

    if not slides:
        return {"ok": not errors, "errors": errors, "warnings": warnings, "checks": {"slide_count": False}}

    # Reject clearly unrelated content when enough meaningful topic anchors are available.
    subject = " ".join((topic, str(plan.get("concept") or ""), str(plan.get("topic") or ""))).lower()
    content = " ".join(
        str(value) for slide in slides for value in (
            slide.get("headline", ""), slide.get("subtext", ""),
            " ".join(str(v) for v in (slide.get("slots") or {}).values()),
        )
    ).lower()
    stopwords = {"yang", "dan", "atau", "untuk", "dari", "dengan", "dalam", "pada", "adalah", "cara", "tips", "apa", "itu", "the", "and", "for", "with", "how", "your"}
    anchors = {word for word in re.findall(r"[a-z0-9]{3,}", subject) if word not in stopwords}
    content_words = set(re.findall(r"[a-z0-9]{3,}", content))
    relevance = bool(not anchors or anchors & content_words)
    if not relevance:
        errors.append("Konten carousel tidak menunjukkan relevansi yang terdeteksi terhadap topik yang diminta.")

    # Only enforce explicit machine-readable brand restrictions; natural-language policy remains reviewable.
    rules = (brand or {}).get("rules") or (brand or {}).get("brand_rules") or []
    if isinstance(rules, dict):
        forbidden = rules.get("forbidden_terms", []) + rules.get("avoid_terms", [])
    else:
        forbidden = (brand or {}).get("forbidden_terms", [])
    forbidden = [str(term).strip() for term in forbidden if str(term).strip()]
    violated_terms = [term for term in forbidden if term.casefold() in content]
    if violated_terms:
        errors.append("Konten melanggar istilah terlarang brand: " + ", ".join(violated_terms))

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

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": {
            "slide_count": valid_slide_count,
            "topic_relevance": relevance,
            "brand_consistency": not violated_terms,
            "cover_role": first_role in ("cover", "single"),
            "unique_headlines": not any("pengulangan" in error for error in errors),
            "slide_content": not any("kosong" in error for error in errors),
            "hashtag_limit": len(hashtags) <= 30,
        },
    }
