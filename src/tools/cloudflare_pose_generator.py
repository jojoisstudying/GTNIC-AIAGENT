"""Optional Cloudflare image editing with local cache and mandatory human review."""
import base64
import hashlib
import io
from pathlib import Path
import re
import uuid

import requests
from PIL import Image

from src import config
from src.tools import asset_library

DEFAULT_MODEL = "@cf/black-forest-labs/flux-2-klein-9b"
CUTOUT_VERSION = "rembg-u2net-v1"
_REMBG_SESSION = None
POSE_GUIDANCE = {
    "senyum": "standing naturally and smiling warmly at the camera",
    "mikir": "thoughtful professional pose, one hand gently at chin",
    "menunjuk": "professional pointing gesture to empty space on the left",
    "pegang_laptop": "standing while holding an open laptop naturally",
    "pegang_tablet": "standing while holding a tablet at waist height",
    "tangan_disilang": "confident professional pose with arms comfortably crossed",
}


def _cache_key(person_id: str, source: bytes, pose: str, prompt: str, model: str) -> str:
    digest = hashlib.sha256(source).hexdigest()
    value = "\0".join((person_id, digest, pose, prompt, model))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _extract_image(response: requests.Response) -> bytes:
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("image/"):
        return response.content
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Workers AI mengembalikan respons yang bukan gambar/JSON") from exc
    result = payload.get("result") or {}
    image = result.get("image") or result.get("images")
    if isinstance(image, list):
        image = image[0] if image else None
    if not isinstance(image, str):
        raise RuntimeError(f"Respons Workers AI tidak berisi result.image: {payload.get('errors')}")
    if image.startswith("data:") and "," in image:
        image = image.split(",", 1)[1]
    try:
        return base64.b64decode(image, validate=True)
    except ValueError as exc:
        raise RuntimeError("Output gambar Workers AI bukan Base64 valid") from exc


def _prepare_reference(source: bytes) -> bytes:
    """FLUX Klein reference inputs must be smaller than 512x512."""
    try:
        with Image.open(io.BytesIO(source)) as image:
            image = image.convert("RGB")
            image.thumbnail((511, 511), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
    except Exception as exc:
        raise RuntimeError("Foto referensi tidak bisa diproses") from exc


def _remove_background(image_bytes: bytes) -> bytes:
    """Return a tightly cropped transparent PNG using the local rembg model."""
    global _REMBG_SESSION
    try:
        from rembg import new_session, remove

        if _REMBG_SESSION is None:
            _REMBG_SESSION = new_session("u2net")
        cutout = remove(image_bytes, session=_REMBG_SESSION)
        with Image.open(io.BytesIO(cutout)) as image:
            image = image.convert("RGBA")
            alpha = image.getchannel("A")
            bbox = alpha.getbbox()
            if bbox is None or alpha.getextrema() == (255, 255):
                raise RuntimeError("mask tidak menghasilkan transparansi")
            left, top, right, bottom = bbox
            pad_x, pad_y = max(4, image.width // 50), max(4, image.height // 50)
            bbox = (max(0, left - pad_x), max(0, top - pad_y),
                    min(image.width, right + pad_x), min(image.height, bottom + pad_y))
            output = io.BytesIO()
            image.crop(bbox).save(output, format="PNG", optimize=True)
            return output.getvalue()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "Gagal menghapus background otomatis. Pastikan rembg dapat mengunduh model u2net; "
            "gambar opaque tidak disimpan sebagai cutout."
        ) from exc


def quality_check_generated(image_path: str | Path) -> dict:
    """Deterministic QC for generated cutout: readability, alpha, crop, and basic image sanity."""
    path = Path(image_path)
    issues = []
    if not path.is_file():
        return {"ok": False, "issues": [f"file tidak ditemukan: {path}"], "metrics": {}}
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            if image.format != "PNG":
                issues.append("hasil cutout bukan PNG")
            if width < 64 or height < 64:
                issues.append(f"resolusi cutout terlalu kecil: {width}x{height}")
            aspect_ratio = round(width / height, 4) if height else 0.0
            if width >= height:
                issues.append("bentuk cutout bukan portrait (tinggi harus melebihi lebar)")
            if image.mode != "RGBA":
                issues.append("PNG tidak memiliki channel RGBA")
                alpha_extrema = None
                transparent_ratio = 0.0
            else:
                alpha = image.getchannel("A")
                alpha_extrema = alpha.getextrema()
                transparent_ratio = alpha.histogram()[0] / (width * height)
                if alpha_extrema[0] == 255:
                    issues.append("background masih opaque; tidak ada transparansi")
                if transparent_ratio > 0.92:
                    issues.append("subjek hampir tidak terdeteksi (lebih dari 92% transparan)")
            metrics = {"width": width, "height": height, "aspect_ratio": aspect_ratio, "mode": image.mode,
                       "alpha_extrema": alpha_extrema, "transparent_ratio": round(transparent_ratio, 4)}
    except Exception as exc:
        return {"ok": False, "issues": [f"gambar rusak/tidak bisa dibaca: {exc}"], "metrics": {}}
    return {"ok": not issues, "issues": issues, "metrics": metrics}


def stage_cutout_from_asset(asset: dict, *, ctx=None) -> dict:
    """Create a review-gated local cutout from an existing opaque generated image."""
    source_path = Path(asset["path"])
    if not source_path.is_file():
        raise FileNotFoundError(f"Image asset lama hilang: {source_path}")
    source_bytes = source_path.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    person_id = asset.get("person_id") or "unknown"
    pose = next(iter(asset.get("tags") or []), "pose")
    model = asset.get("model") or "unknown"
    key = hashlib.sha256(f"{digest}\0{CUTOUT_VERSION}".encode("utf-8")).hexdigest()
    cached = asset_library.find_cached(key)
    if cached:
        return {**cached, "cached": True}

    cutout = _remove_background(source_bytes)
    output_dir = config.ROOT / "data" / "assets" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{person_id}_{pose}_{key[:16]}_cutout.png"
    output_path.write_bytes(cutout)
    qc = quality_check_generated(output_path)
    if not qc["ok"]:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"QC cutout gagal: {qc['issues']}")
    asset_id = asset_library.add_asset(
        str(output_path), [pose], f"CUTOUT dari asset {asset['id']}; menunggu review.",
        status="pending_review", person_id=asset.get("person_id"),
        source_path=str(source_path), model=model,
        prompt=f"Local background removal from approved asset {asset['id']}", cache_key=key,
        kind="cutout", run_id=ctx.run_id if ctx else None,
    )
    return {"id": asset_id, "path": str(output_path), "tags": [pose], "status": "pending_review",
            "person_id": asset.get("person_id"), "source_path": str(source_path), "model": model,
            "cache_key": key, "cached": False}


def generate_pose(person_id: str, pose: str, custom_prompt: str = "", *, force: bool = False,
                  ctx=None) -> dict:
    """Create/cache an image variant as pending_review; never auto-approve it."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", pose):
        raise ValueError("pose tag may contain only letters, numbers, underscore, and hyphen")
    if pose not in POSE_GUIDANCE and not custom_prompt.strip():
        raise ValueError(f"Pose '{pose}' belum punya arahan; sertakan custom_prompt")
    source_path = asset_library.get_person_reference(person_id)
    if not source_path:
        raise FileNotFoundError(f"Foto referensi data/people/{person_id}/reference.* belum terdaftar")
    source = Path(source_path).read_bytes()
    model = config.opt("CLOUDFLARE_IMAGE_MODEL", DEFAULT_MODEL)
    prompt = custom_prompt.strip() or POSE_GUIDANCE[pose]
    full_prompt = (
        "Edit the provided reference photo into a realistic corporate industrial workplace portrait. "
        "Preserve the same adult person's identity, facial features, skin tone, hairstyle and work uniform. "
        "Only change body pose as requested: " + prompt + ". Keep realistic anatomy, hands, lighting, "
        "camera perspective and natural photographic texture. Keep PPE and safety details physically correct. "
        "No text, no logos, no watermark, no extra people, no illustration, no plastic skin."
    )
    generation_key = _cache_key(person_id, source, pose, full_prompt, model)
    key = hashlib.sha256(f"{generation_key}\0{CUTOUT_VERSION}".encode("utf-8")).hexdigest()
    cached = asset_library.find_cached(key)
    if cached and not force:
        return {**cached, "cached": True}
    # Upgrade assets generated by older versions without paying for another image generation.
    legacy = asset_library.find_cached(generation_key)
    if legacy and not force and Path(legacy["path"]).is_file():
        cutout = _remove_background(Path(legacy["path"]).read_bytes())
        output_dir = config.ROOT / "data" / "assets" / "generated"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{person_id}_{pose}_{key[:16]}_cutout.png"
        output_path.write_bytes(cutout)
        asset_id = asset_library.add_asset(
            str(output_path), [pose], f"GENERATED CUTOUT ({CUTOUT_VERSION}); menunggu review. Person={person_id}",
            status="pending_review", person_id=person_id, source_path=source_path,
            model=model, prompt=full_prompt, cache_key=key, kind="cutout",
            run_id=ctx.run_id if ctx else None,
        )
        return {"id": asset_id, "path": str(output_path), "tags": [pose], "status": "pending_review",
                "person_id": person_id, "source_path": source_path, "model": model,
                "prompt": full_prompt, "cache_key": key, "cached": False,
                "generation_reused": True, "cutout": True}
    if force:
        key = hashlib.sha256(f"{key}\0{uuid.uuid4().hex}".encode("utf-8")).hexdigest()

    account_id, token = config.need("CLOUDFLARE_ACCOUNT_ID"), config.need("CLOUDFLARE_API_TOKEN")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    reference = _prepare_reference(source)
    request_args = {
        "headers": {"Authorization": f"Bearer {token}"},
        "data": {"prompt": full_prompt, "width": "1024", "height": "1280"},
        "files": {"input_image_0": ("reference.png", reference, "image/png")},
        "timeout": 180,
    }
    if ctx and ctx.http:
        response = ctx.http.request("POST", url, step="designer", provider="cloudflare", **request_args)
    else:
        response = requests.post(url, **request_args)
    if not response.ok:
        raise RuntimeError(f"Workers AI HTTP {response.status_code}: {response.text[:1000]}")

    image_bytes = _remove_background(_extract_image(response))

    output_dir = config.ROOT / "data" / "assets" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{person_id}_{pose}_{key[:16]}_cutout.png"
    output_path.write_bytes(image_bytes)
    qc = quality_check_generated(output_path)
    if not qc["ok"]:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"QC gambar hasil generate gagal: {qc['issues']}")
    asset_id = asset_library.add_asset(
        str(output_path), [pose], f"GENERATED CUTOUT ({CUTOUT_VERSION}); menunggu review. Person={person_id}",
        status="pending_review", person_id=person_id, source_path=source_path,
        model=model, prompt=full_prompt, cache_key=key, kind="pose",
        run_id=ctx.run_id if ctx else None,
    )
    return {"id": asset_id, "path": str(output_path), "tags": [pose], "status": "pending_review",
            "person_id": person_id, "source_path": source_path, "model": model,
            "prompt": full_prompt, "cache_key": key, "cached": False}
