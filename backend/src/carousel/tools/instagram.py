"""Tool Instagram (Instagram API with Instagram Login). Token hanya dibaca di sini, tidak pernah masuk prompt LLM.
Detail endpoint bisa berubah: cek dokumentasi Meta 'Instagram Platform > Content Publishing' bila ada error."""
import time
import requests
from src import config
from src.core.http import HttpClient, redact_text


def _base() -> str:
    return config.opt("IG_API_BASE", "https://graph.instagram.com")


def _check(r) -> dict:
    data = r.json()
    if "error" in data:
        err = data["error"]
        msg = err.get("message", "error tidak diketahui")
        if err.get("code") == 190:
            msg += " (token tidak valid/kedaluwarsa: generate ulang di dashboard Meta dan perbarui .env)"
        raise RuntimeError(f"Instagram API error: {msg}")
    return data


def _post(path: str, *, ctx=None, **data) -> dict:
    token = config.need("IG_TOKEN")
    url = f"{_base()}/{path}"
    if ctx and ctx.http:
        response = ctx.http.request("POST", url, step="instagram", provider="instagram",
                                    data={**data, "access_token": token}, timeout=60)
    else:
        response = requests.post(url, data={**data, "access_token": token}, timeout=60)
    try:
        return _check(response)
    except RuntimeError as exc:
        raise RuntimeError(redact_text(str(exc))) from None


def _get(path: str, *, ctx=None, **params) -> dict:
    token = config.need("IG_TOKEN")
    url = f"{_base()}/{path}"
    if ctx and ctx.http:
        response = ctx.http.request("GET", url, step="instagram", provider="instagram",
                                    params={**params, "access_token": token}, timeout=60)
    else:
        response = requests.get(url, params={**params, "access_token": token}, timeout=60)
    try:
        return _check(response)
    except RuntimeError as exc:
        raise RuntimeError(redact_text(str(exc))) from None


def wait_until_ready(container_id: str, timeout: int = 90, interval: int = 3, *, ctx=None) -> None:
    """Wait until a media container finishes; propagate unreadable status errors."""
    waited = 0
    while waited <= timeout:
        try:
            status = _get(container_id, fields="status_code", ctx=ctx).get("status_code")
        except Exception:
            raise
        if status in (None, "FINISHED"):
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Container {container_id} berstatus {status}")
        time.sleep(interval)
        waited += interval
    raise RuntimeError(f"Container {container_id} belum siap setelah {timeout} detik")


def publish_image(image_url: str, caption: str, *, ctx=None) -> str:
    uid = config.need("IG_USER_ID")
    cid = _post(f"{uid}/media", ctx=ctx, image_url=image_url, caption=caption)["id"]
    wait_until_ready(cid, ctx=ctx)
    return _post(f"{uid}/media_publish", ctx=ctx, creation_id=cid)["id"]


def publish_carousel(image_urls: list[str], caption: str, *, ctx=None) -> str:
    """Carousel 2-10 gambar JPEG berURL publik. Alur: container per gambar -> container carousel -> publish."""
    if not 2 <= len(image_urls) <= 10:
        raise ValueError("Carousel Instagram harus 2-10 gambar")
    uid = config.need("IG_USER_ID")
    children = [_post(f"{uid}/media", ctx=ctx, image_url=u, is_carousel_item="true")["id"] for u in image_urls]
    for c in children:
        wait_until_ready(c, ctx=ctx)
    parent = _post(f"{uid}/media", ctx=ctx, media_type="CAROUSEL", children=",".join(children), caption=caption)["id"]
    wait_until_ready(parent, ctx=ctx)
    return _post(f"{uid}/media_publish", ctx=ctx, creation_id=parent)["id"]


def publish_reels(video_url: str, caption: str, *, ctx=None) -> str:
    """Publikasikan video MP4 publik sebagai Instagram Reels."""
    uid = config.need("IG_USER_ID")
    cid = _post(f"{uid}/media", ctx=ctx, media_type="REELS", video_url=video_url, caption=caption)["id"]
    wait_until_ready(cid, timeout=180, interval=5, ctx=ctx)
    return _post(f"{uid}/media_publish", ctx=ctx, creation_id=cid)["id"]


def get_media_metrics(media_id: str, *, ctx=None) -> dict:
    try:
        return _get(media_id, fields="id,like_count,comments_count,timestamp,permalink", ctx=ctx)
    except Exception:  # permalink kadang tak tersedia; ulangi dengan field dasar
        return _get(media_id, fields="id,like_count,comments_count,timestamp", ctx=ctx)


def get_content_publishing_limit(*, ctx=None) -> dict:
    """Query content_publishing_limit for the configured Instagram account.

    Returns dict with quota_usage and config details.
    """
    uid = config.need("IG_USER_ID")
    data = _get(f"{uid}/content_publishing_limit", fields="quota_usage,config", ctx=ctx)
    items = data.get("data", [])
    if items:
        return items[0]
    return data


def get_my_recent_performance(*, ctx=None) -> dict:
    """Dipakai Agent 1 (riset): 10 post terakhir + like/komentar."""
    try:
        uid = config.need("IG_USER_ID")
        data = _get(f"{uid}/media", fields="id,caption,timestamp,like_count,comments_count", limit=10, ctx=ctx)
        posts = [{**p, "caption": (p.get("caption") or "")[:120]} for p in data.get("data", [])]
        return {"posts": posts, "post_count": len(posts), "enough_data": len(posts) >= 5}
    except Exception as e:
        return {"posts": [], "post_count": 0, "enough_data": False, "error": f"{type(e).__name__}: {e}"}