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


def wait_until_ready(container_id: str, timeout: int = 90, interval: int = 3, *, ctx=None,
                     with_detail: bool = False) -> None:
    """Wait until a media container finishes; propagate unreadable status errors.

    `with_detail=True` (dipakai Reels) ikut meminta field `status` agar pesan error dari Meta
    (mis. format video tidak didukung) ikut tampil di pesan kegagalan.
    """
    waited = 0
    fields = "status_code,status" if with_detail else "status_code"
    while waited <= timeout:
        try:
            data = _get(container_id, fields=fields, ctx=ctx)
        except Exception:
            raise
        status = data.get("status_code")
        if status in (None, "FINISHED"):
            return
        if status in ("ERROR", "EXPIRED"):
            extra = f": {data['status']}" if with_detail and data.get("status") else ""
            raise RuntimeError(f"Container {container_id} berstatus {status}{extra}")
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


def publish_reel(video_url: str, caption: str, *, share_to_feed: bool = True, ctx=None,
                 timeout: int = 300) -> str:
    """Reels: MP4/MOV (H.264 + AAC) berURL publik, vertikal 9:16, 3-90 detik. Alur: container REELS ->
    tunggu pemrosesan video (jauh lebih lama dari gambar) -> publish. Cek dokumentasi Meta 'Content
    Publishing > Reels' bila parameter berubah."""
    uid = config.need("IG_USER_ID")
    cid = _post(f"{uid}/media", ctx=ctx, media_type="REELS", video_url=video_url, caption=caption,
                share_to_feed="true" if share_to_feed else "false")["id"]
    wait_until_ready(cid, timeout=timeout, interval=5, ctx=ctx, with_detail=True)
    return _post(f"{uid}/media_publish", ctx=ctx, creation_id=cid)["id"]


def get_media_metrics(media_id: str, *, ctx=None) -> dict:
    try:
        return _get(media_id, fields="id,like_count,comments_count,timestamp,permalink", ctx=ctx)
    except Exception:  # permalink kadang tak tersedia; ulangi dengan field dasar
        return _get(media_id, fields="id,like_count,comments_count,timestamp", ctx=ctx)


def get_media_insights(media_id: str, *, ctx=None) -> dict:
    """Ambil insight per media. Metrik yang tidak tersedia untuk tipe media dilewati (tetap NULL)."""
    out: dict = {}
    for metric in ("reach", "saved", "shares", "views", "total_interactions", "profile_visits", "follows"):
        try:
            data = _get(f"{media_id}/insights", ctx=ctx, metric=metric)
            vals = data.get("data") or []
            if vals and vals[0].get("values"):
                out[metric] = vals[0]["values"][0].get("value")
        except Exception:
            continue
    return out


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