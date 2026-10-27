"""AGENT 3: Designer. Rencana Agent 2 -> file JPEG per slide.
Tools: asset_library (cari pose), compositor (render), qc (cek kode). Tanpa LLM: deterministik & konsisten brand."""
import json
import hashlib
import re
from pathlib import Path
from PIL import Image
from src import config
from src.core.context import RunContext
from src.layouts import registry as layout_registry
from src.layouts.models import LayoutError
from src.layouts.style.packs import build_pack
from src.render.assemble import render_layout_html
from src.render.renderer import RenderError, Renderer
from src.tools import qc_dom
from src.tools import asset_library, cloudflare_pose_generator, compositor, qc


def contact_sheet(paths: list[str], out: str) -> str:
    ims = [Image.open(p) for p in paths]
    h = 700
    ims = [im.resize((int(im.width * h / im.height), h)) for im in ims]
    sheet = Image.new("RGB", (sum(i.width for i in ims) + 20 * (len(ims) + 1), h + 40), (28, 28, 28))
    x = 20
    for im in ims:
        sheet.paste(im, (x, 20))
        x += im.width + 20
    sheet.save(out, "JPEG", quality=88)
    return out


def _html_slots(spec, slide: dict) -> tuple[dict, dict, list[str]]:
    """Map the planner's concise slide fields to a validated HTML layout schema."""
    headline = str(slide.get("headline", ""))
    subtext = str(slide.get("subtext", ""))
    source_slots = dict(slide.get("slots") or {})
    source_params = dict(slide.get("params") or {})
    emphasis = slide.get("emphasis") or []
    if spec.id == "perbandingan_dua_kolom":
        source_slots.setdefault("left_items", source_params.get("left_items", []))
        source_slots.setdefault("right_items", source_params.get("right_items", []))
        if not source_slots["left_items"] and source_params.get("left_text"):
            source_slots["left_items"] = [str(source_params["left_text"])]
        if not source_slots["right_items"] and source_params.get("right_text"):
            source_slots["right_items"] = [str(source_params["right_text"])]
    if isinstance(emphasis, str):
        emphasis = ([headline.split()[0]] if emphasis == "headline" and headline else
                    [subtext.split()[0]] if emphasis == "subtext" and subtext else
                    [] if emphasis in {"headline", "subtext"} else [emphasis])
    else:
        emphasis = [
            headline.split()[0] if item == "headline" and headline else
            subtext.split()[0] if item == "subtext" and subtext else
            str(item)
            for item in emphasis
            if item not in {"headline", "subtext"} or
            (item == "headline" and headline) or (item == "subtext" and subtext)
        ]
    if "items" in source_params and "points" not in source_slots:
        source_slots["points"] = source_params["items"]

    defaults = {
        "title": headline,
        "label": headline,
        "kicker": "",
        "subtitle": subtext,
        "body": subtext,
        "context": subtext,
        "keyword": (source_slots.get("keyword") or "").strip() or "KOMENTAR",
        "verb": source_slots.get("verb", ""),
        "secondary": source_slots.get("secondary", ""),
        "source": source_slots.get("source", ""),
        "icon": source_slots.get("icon", "alert"),
        "left_label": source_slots.get("left_label", "Sebelum"),
        "right_label": source_slots.get("right_label", "Sesudah"),
    }
    slots = {name: source_slots.get(name, defaults.get(name, "")) for name in spec.slots}
    for name, slot_spec in spec.slots.items():
        value = slots[name]
        if slot_spec.type == "list" and not value:
            if name in {"points", "left_items", "right_items"}:
                value = list(source_params.get("items", [])) if name == "points" else []
                if not value:
                    value = [part.strip() for part in re.split(r"[.!?;]\s*", subtext) if part.strip()]
                value = value[:slot_spec.max_items] if slot_spec.max_items else value
            else:
                value = []
            slots[name] = value
    params = {name: source_params[name] for name in spec.params if name in source_params}
    return slots, params, [str(item) for item in emphasis if item]


def _render_html_slide(renderer: Renderer, spec, slide: dict, photo: str | None,
                       brand: dict, params: dict, out_path: Path, index: int,
                       total: int, style_pack: dict) -> tuple[dict, list[str]]:
    slots, layout_params, emphasis = _html_slots(spec, slide)
    layout_params.update({key: str(value) for key, value in params.items() if key in spec.params})
    photo_url = Path(photo).resolve().as_uri() if photo and Path(photo).is_file() else None
    html = render_layout_html(spec, slots, layout_params, emphasis, style_pack,
                              index - 1, total, brand, photo_url=photo_url)
    result = renderer.render(html, out_path)
    dom_issues = qc_dom.evaluate(result.report)
    blocking = [f"{issue.code}: {issue.detail}" for issue in dom_issues if issue.severity == "error"]
    meta = {
        "layout_id": spec.id,
        "path": str(result.path),
        "has_photo": bool(photo_url),
        "photo_path": photo if photo_url else None,
        "overflow": any(not item.get("fits", True) for item in result.report),
        "headline_size": max((item.get("font_px", 0) for item in result.report
                              if item.get("slot") in {"title", "label"}), default=72),
        "subtext_size": max((item.get("font_px", 0) for item in result.report
                             if item.get("slot") in {"subtitle", "body", "context"}), default=32),
        "text_bottom": max((item.get("bbox", {}).get("y", 0) + item.get("bbox", {}).get("h", 0)
                             for item in result.report if item.get("kind") == "text" and item.get("slot")), default=0),
        "limit_bottom": qc_dom.FOOTER_TOP,
        "dom_issues": [{"code": issue.code, "severity": issue.severity,
                         "element": issue.element, "detail": issue.detail} for issue in dom_issues],
        "render_ms": result.ms,
        "blocked_requests": result.blocked,
    }
    return meta, blocking


def _brand_supports_html(brand: dict) -> bool:
    """Legacy unit fixtures may use a minimal brand without HTML chrome settings."""
    colors = brand.get("colors") or {}
    tokens = brand.get("tokens") or {}
    has_bg = bool(tokens.get("bg") or colors.get("primary"))
    has_accent = bool(tokens.get("accent") or colors.get("accent"))
    return has_bg and has_accent


def run(plan: dict, brand: dict, out_dir, on_step=print, *, ctx: RunContext | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("slide_*.jpg"):
        old.unlink()

    renderer_mode = config.opt("RENDERER", "html").strip().lower()
    if renderer_mode not in {"html", "pillow"}:
        raise ValueError(f"RENDERER harus 'html' atau 'pillow', bukan {renderer_mode!r}")
    html_renderer = None
    style_pack = None
    if renderer_mode == "html" and not _brand_supports_html(brand):
        renderer_mode = "pillow"
    if renderer_mode == "html":
        try:
            html_renderer = Renderer().__enter__()
            style_pack = build_pack(int((plan.get("style") or {}).get("seed", 2)), brand,
                                    max(1, len(plan.get("slides", []))))
        except Exception:
            if html_renderer is not None:
                html_renderer.__exit__(None, None, None)
            raise

    warnings = list(qc.check_brand(brand))
    slides, missing, pending_review, step_no = [], [], [], 0
    generation_enabled = config.opt("CLOUDFLARE_POSE_GENERATION", "true").lower() in {"1", "true", "yes", "on"}
    person_id = config.opt("CLOUDFLARE_POSE_PERSON_ID") or (brand.get("pose_generation") or {}).get("person_id")
    total = len(plan["slides"])
    generated_pose_tags = set()
    for i, s in enumerate(plan["slides"], 1):
        role = s.get("role", "single")
        step_no += role == "content"
        tags = s.get("pose_tags", [])
        photo = asset_library.find_pose(tags) if tags else None
        # A placeholder is only for internal layout tests; never show it in the working carousel.
        if photo and asset_library.is_placeholder(photo):
            photo = None
        if tags and photo and not asset_library.is_cutout(photo):
            old_generated = asset_library.find_opaque_generated_pose(tags)
            if old_generated:
                try:
                    staged = cloudflare_pose_generator.stage_cutout_from_asset(old_generated, ctx=ctx)
                    if not any(a["id"] == staged["id"] for a in pending_review):
                        staged_qc = cloudflare_pose_generator.quality_check_generated(staged["path"])
                        pending_review.append({"id": staged["id"], "pose": tags[0], "path": staged["path"],
                                               "qc": staged_qc})
                    # Do not render an old factory-background image while its cutout awaits review.
                    photo = None
                except Exception as exc:
                    warnings.append(f"Cutout pose {tags} gagal dibuat lokal: {exc}")
        elif tags and not photo:
            old_generated = asset_library.find_opaque_generated_pose(tags)
            if old_generated:
                try:
                    staged = cloudflare_pose_generator.stage_cutout_from_asset(old_generated, ctx=ctx)
                    if not any(a["id"] == staged["id"] for a in pending_review):
                        staged_qc = cloudflare_pose_generator.quality_check_generated(staged["path"])
                        pending_review.append({"id": staged["id"], "pose": tags[0], "path": staged["path"],
                                               "qc": staged_qc})
                except Exception as exc:
                    warnings.append(f"Cutout pose {tags} gagal dibuat lokal: {exc}")
        legacy_was_staged = any(a["pose"] in tags for a in pending_review)
        tags_to_generate = [tag for tag in tags if tag not in generated_pose_tags]
        if (generation_enabled and person_id and tags_to_generate and not legacy_was_staged
                and (not photo or asset_library.is_placeholder(photo))):
            for tag in tags_to_generate:
                generated_pose_tags.add(tag)
                try:
                    staged = (cloudflare_pose_generator.generate_pose(person_id, tag, ctx=ctx)
                              if ctx else cloudflare_pose_generator.generate_pose(person_id, tag))
                    staged_qc = cloudflare_pose_generator.quality_check_generated(staged["path"])
                    staged["qc"] = staged_qc
                    if staged["status"] == "pending_review" and not any(a["id"] == staged["id"] for a in pending_review):
                        pending_review.append({"id": staged["id"], "pose": tag, "path": staged["path"],
                                               "qc": staged_qc})
                except Exception as exc:
                    warnings.append(f"Pose {tag} belum bisa digenerate: {exc}")
            # A generated result is pending until reviewed, so continue using only an approved library item.
            photo = asset_library.find_pose(tags)
            if photo and asset_library.is_placeholder(photo):
                photo = None
        if tags and not photo:
            missing += tags
        on_step(f"[designer] slide {i}/{total} ({role}) pose={tags or '-'} -> {photo or 'tanpa foto'}")
        layout_id = s.get("layout_id")
        params = dict(s.get("params") or {})
        params.update({"index": i, "total": total, "step_no": step_no, "role": role})

        if renderer_mode == "html":
            if html_renderer is None or style_pack is None:
                raise RenderError("HTML renderer tidak berhasil diinisialisasi")
            layout_id = _resolve_html_layout_id(layout_id, role, photo, s)
            spec = layout_registry.get(layout_id)
            if spec.meta.status != "approved":
                raise LayoutError(f"layout '{layout_id}' berstatus {spec.meta.status}; hanya layout approved yang bisa dirender")
            content_roles = {"konteks", "penjelasan", "langkah", "daftar", "data",
                             "perbandingan", "bukti", "rangkuman"}
            compatible_role = (
                spec.meta.role == role
                or (role == "content" and spec.meta.role in content_roles)
                or (role == "single" and spec.meta.role in {"cover", "cta"})
            )
            if not compatible_role:
                raise LayoutError(f"layout '{layout_id}' role={spec.meta.role} tidak cocok dengan slide role={role}")
            meta, dom_errors = _render_html_slide(
                html_renderer, spec, s, photo, brand, params,
                out_dir / f"slide_{i:02d}.jpg", i, total, style_pack,
            )
            meta["role"] = role
            meta["index"] = i
            meta["issues"] = dom_errors
            if any(issue["severity"] == "warn" for issue in meta["dom_issues"]):
                warnings.extend(f"slide {i}: {issue['code']} - {issue['detail']}"
                                for issue in meta["dom_issues"] if issue["severity"] == "warn")
        elif layout_id:
            from src.layouts import get_layout_renderer
            renderer = get_layout_renderer(layout_id)
            meta = renderer(
                text={"headline": s["headline"], "subtext": s.get("subtext", "")},
                photo_path=photo,
                brand=brand,
                params=params,
                out_path=out_dir / f"slide_{i:02d}.jpg"
            )
            meta["role"] = role
            meta["index"] = i
        else:
            meta = compositor.render_slide(role, s["headline"], s.get("subtext", ""), photo, brand,
                                           out_dir / f"slide_{i:02d}.jpg", index=i, total=total, step_no=step_no)
            meta["issues"] = qc.check_slide(meta)
        meta["placeholder"] = asset_library.is_placeholder(photo)
        slides.append(meta)
        if ctx:
            slide_path = Path(meta["path"])
            asset_library.add_asset(str(slide_path), [], f"Rendered slide {i}",
                                    status="approved", run_id=ctx.run_id, kind="slide")

    if any(m["placeholder"] for m in slides):
        warnings.append("Poster memakai FOTO PLACEHOLDER. Jangan diposting; ganti dengan foto karyawan asli.")
    if missing:
        warning = f"Pose belum ada sebagai asset foto siap pakai: {sorted(set(missing))} (placeholder disembunyikan; slide dibuat tanpa foto)"
        if not generation_enabled:
            warning += ". Untuk meminta Designer membuat pose yang belum ada, aktifkan CLOUDFLARE_POSE_GENERATION=true di .env"
        warnings.append(warning)
    if pending_review:
        warnings.append("QC otomatis selesai; hasil pose menunggu persetujuan manusia: " +
                        ", ".join(f"ID {a['id']} ({a['pose']}, QC={'OK' if a.get('qc', {}).get('ok') else 'GAGAL'})"
                                  for a in pending_review))
    try:
        sheet = contact_sheet([m["path"] for m in slides], str(out_dir / "preview.jpg"))
        ok = not warnings_blocking(warnings) and all(not m["issues"] for m in slides)
        result = {"ok": ok, "renderer": renderer_mode, "style": plan.get("style", {}),
                  "slides": slides, "warnings": warnings, "preview": sheet,
                  "missing_poses": sorted(set(missing)), "pending_review": pending_review}
        if ctx:
            preview_path = Path(sheet)
            asset_library.add_asset(str(preview_path), [], "Rendered contact-sheet preview",
                                    status="approved", run_id=ctx.run_id, kind="preview")
        if not ctx:
            (config.OUTPUT_DIR / "design_latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if html_renderer is not None:
            html_renderer.__exit__(None, None, None)


def _default_html_layout(role: str, photo: str | None) -> str:
    """Choose an approved registry layout when an older plan lacks a usable ID."""
    choices = {
        "cover": "cover_foto_judul_bawah" if photo else "cover_judul_raksasa",
        "cta": "cta_komen",
        "content": "penjelasan_split_foto" if photo else "penjelasan_teks_ikon",
        "single": "cover_foto_judul_bawah" if photo else "cover_judul_raksasa",
    }
    return choices.get(role, "penjelasan_teks_ikon")


def _resolve_html_layout_id(layout_id: str | None, role: str, photo: str | None,
                            slide: dict | None = None) -> str:
    """Translate saved Pillow-era plans to equivalent approved HTML layouts."""
    aliases = {
        "foto_penuh_overlay": "cover_judul_raksasa",
        "split_foto_teks": "penjelasan_split_foto",
        "angka_besar": "penjelasan_teks_ikon",
        "kutipan": "penjelasan_teks_ikon",
        "daftar_bernomor": "daftar_bernomor",
        "perbandingan": "perbandingan_dua_kolom",
        "tipografi_minimal": "penjelasan_teks_ikon",
        "langkah_diagram": "daftar_bernomor",
        "cta_blok": "cta_komen",
    }
    candidate = aliases.get(layout_id, layout_id) if layout_id else _default_html_layout(role, photo)
    try:
        spec = layout_registry.get(candidate)
    except LayoutError:
        return _default_html_layout(role, photo)
    if spec.meta.status != "approved":
        return _default_html_layout(role, photo)
    if role == "cover" and spec.meta.role != "cover":
        return _default_html_layout(role, photo)
    if role == "cta" and spec.meta.role != "cta":
        return _default_html_layout(role, photo)
    if role in {"content", "single"} and spec.meta.role in {"cover", "cta"}:
        return _default_html_layout(role, photo)
    # Self-healing: jika layout butuh foto tapi tidak ada foto yang tersedia/valid
    if spec.meta.needs_photo == "required" and not photo:
        return _default_html_layout(role, photo)
    if spec.id == "daftar_bernomor" and slide:
        raw_slots = slide.get("slots") or {}
        raw_params = slide.get("params") or {}
        points = raw_slots.get("points") or raw_params.get("items") or []
        if len(points) < spec.slots["points"].min_items:
            return "penjelasan_split_foto" if photo else "penjelasan_teks_ikon"
    return spec.id


def warnings_blocking(warnings: list[str]) -> list[str]:
    """Peringatan brand (kontras) menggagalkan; placeholder/pose hilang hanya informasi."""
    return [w for w in warnings if w.startswith("Kontras")]