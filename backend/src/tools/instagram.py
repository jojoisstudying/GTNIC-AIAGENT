"""Tool Instagram (Instagram API with Instagram Login). Token hanya dibaca di sini, tidak pernah masuk prompt LLM.

Catatan penting:
- Endpoint `graph.instagram.com` (Instagram API with Instagram Login) hanya mendukung akun
  Business/Creator yang login lewat Instagram (bukan Page Facebook). Kalau akun belum
  memenuhi syarat, Meta mengembalikan error 100/190/OAuthException — pesannya diteruskan
  apa adanya (ter-redaksi) supaya operator tahu langkah perbaikannya.
- Metrik insight yang TIDAK didukung untuk tipe media tertentu (mis. `profile_visits` untuk
  Reels, `impressions` untuk semua tipe saat ini) dikembalikan 400 oleh Meta. Nilai seperti
  itu dibiarkan NULL — bukan 0 — agar UI bisa membedakan "belum tersedia" dari "nol".
"""
import time

import requests

from src import config
from src.core.http import HttpClient, HttpError, redact_text

# Metrik insight yang didukung per media product type (hasil audit langsung ke Graph API).
INSIGHT_METRICS = ("reach", "saved", "shares", "views", "total_interactions", "profile_visits", "follows")
BASIC_MEDIA_FIELDS = "id,media_type,media_product_type,timestamp,permalink,like_count,comments_count,caption"


def _base() -> str:
    return config.opt("IG_API_BASE", "https://graph.instagram.com")


def _check(r) -> dict:
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f"Instagram API mengembalikan respons non-JSON (HTTP {r.status_code})") from None
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        msg = err.get("message", "error tidak diketahui")
        code = err.get("code")
        if code == 190:
            msg += (" (token tidak valid/kedaluwarsa: buat ulang long-lived token di dashboard Meta "
                    "dan perbarui IG_TOKEN di backend/.env)")
        elif code == 100:
            msg += " (parameter/izin tidak didukung untuk tipe akun atau media ini)"
        elif code == 4 or code == 17:
            msg += " (kuota/rate limit Instagram terlampaui; coba lagi nanti)"
        parts = [msg]
        if code not in (None, ""):
            parts.append(f"code={code}")
        if err.get("error_subcode"):
            parts.append(f"subcode={err.get('error_subcode')}")
        raise RuntimeError(redact_text(" | ".join(str(p) for p in parts)))
    return data


def _post(path: str, *, ctx=None, **data) -> dict:
    token = config.need("IG_TOKEN")
    url = f"{_base()}/{path}"
    payload = {**data, "access_token": token}
    if ctx and ctx.http:
        response = ctx.http.request("POST", url, step="instagram", provider="instagram",
                                    data=payload, timeout=60)
    else:
        response = requests.post(url, data=payload, timeout=60)
    return _check(response)


def _get(path: str, *, ctx=None, **params) -> dict:
    token = config.need("IG_TOKEN")
    url = f"{_base()}/{path}"
    query = {**params, "access_token": token}
    if ctx and ctx.http:
        response = ctx.http.request("GET", url, step="instagram", provider="instagram",
                                    params=query, timeout=60)
    else:
        response = requests.get(url, params=query, timeout=60)
    return _check(response)


def wait_until_ready(container_id: str, timeout: int = 90, interval: int = 3, *, ctx=None,
                     with_detail: bool = False) -> None:
    """Wait until a media container finishes; propagate unreadable status errors.

    `with_detail=True` (dipakai Reels) ikut meminta field `status` agar pesan error dari Meta
    (mis. format video tidak didukung) ikut tampil di pesan kegagalan.
    """
    waited = 0
    fields = "status_code,status" if with_detail else "status_code"
    while waited <= timeout:
        data = _get(container_id, fields=fields, ctx=ctx)
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
    children = [_post(f"{uid}/media", ctx=ctx, image_url=u, is_carousel_item="true")["id"]
                for u in image_urls]
    for c in children:
        wait_until_ready(c, ctx=ctx)
    parent = _post(f"{uid}/media", ctx=ctx, media_type="CAROUSEL",
                   children=",".join(children), caption=caption)["id"]
    wait_until_ready(parent, ctx=ctx)
    return _post(f"{uid}/media_publish", ctx=ctx, creation_id=parent)["id"]


def publish_reel(video_url: str, caption: str, *, share_to_feed: bool = True, ctx=None,
                 timeout: int = 300) -> str:
    """Reels: MP4/MOV (H.264 + AAC) berURL publik, vertikal 9:16, 3-90 detik. Alur: container REELS ->
    tunggu pemrosesan video (jauh lebih lama dari gambar) -> publish."""
    uid = config.need("IG_USER_ID")
    cid = _post(f"{uid}/media", ctx=ctx, media_type="REELS", video_url=video_url, caption=caption,
                share_to_feed="true" if share_to_feed else "false")["id"]
    wait_until_ready(cid, timeout=timeout, interval=5, ctx=ctx, with_detail=True)
    return _post(f"{uid}/media_publish", ctx=ctx, creation_id=cid)["id"]


def get_media_metrics(media_id: str, *, ctx=None) -> dict:
    """Field dasar media (like/komentar/permalink). Field yang ditolak dilewati satu per satu."""
    try:
        return _get(media_id, fields=BASIC_MEDIA_FIELDS, ctx=ctx)
    except Exception:
        return _get(media_id, fields="id,like_count,comments_count,timestamp", ctx=ctx)


def get_media_insights(media_id: str, *, ctx=None) -> dict:
    """Ambil insight per media. Metrik yang tidak didukung untuk tipe media dilewati (tetap NULL)."""
    out: dict = {}
    for metric in INSIGHT_METRICS:
        try:
            data = _get(f"{media_id}/insights", ctx=ctx, metric=metric)
        except Exception:
            continue  # 400 = metrik tidak didukung tipe media ini -> biarkan NULL
        for item in data.get("data") or []:
            values = item.get("values") or []
            if values and values[0].get("value") is not None:
                out[item.get("name") or metric] = values[0]["value"]
                break
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
        data = _get(f"{uid}/media", fields="id,caption,timestamp,like_count,comments_count",
                    limit=10, ctx=ctx)
        posts = [{**p, "caption": (p.get("caption") or "")[:120]} for p in data.get("data", [])]
        return {"posts": posts, "post_count": len(posts), "enough_data": len(posts) >= 5}
    except Exception as e:
        return {"posts": [], "post_count": 0, "enough_data": False,
                "error": f"{type(e).__name__}: {redact_text(str(e))}"}


# ---------------------------------------------------------------------------
# Diagnostik koneksi (dipakai UI Koneksi Sosial & Pusat Otomatisasi)
# ---------------------------------------------------------------------------

REQUIRED_ENV = ("IG_USER_ID", "IG_TOKEN", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                "CLOUDINARY_API_SECRET")


def connection_status(*, ctx=None, live: bool = True) -> dict:
    """Periksa kesiapan publikasi Instagram TANPA mempublikasikan apa pun.

    Mengembalikan status konfigurasi + hasil pemeriksaan langsung (username, tipe akun,
    kuota publishing, izin yang benar-benar dimiliki) agar UI bisa menampilkan petunjuk
    konfigurasi yang tepat, bukan sekadar "belum terhubung".
    """
    missing = [k for k in REQUIRED_ENV if not config.opt(k)]
    result: dict = {
        "configured": not missing,
        "missing_env": missing,
        "api_base": _base(),
        "cloudinary": {
            "configured": all(config.opt(k) for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
                                                     "CLOUDINARY_API_SECRET")),
        },
    }
    if missing:
        result["status"] = "not_configured"
        result["hints"] = [
            "Isi variabel berikut di backend/.env lalu restart backend: " + ", ".join(missing),
            "IG_USER_ID = ID akun Instagram Business/Creator (bukan ID postingan).",
            "IG_TOKEN = long-lived access token dari Meta app dengan scope "
            "instagram_business_basic + instagram_business_content_publish.",
            "Cloudinary dipakai hanya sebagai host URL publik media (Instagram tidak menerima upload langsung).",
        ]
        return result
    if not live:
        result["status"] = "configured"
        return result

    checks: dict = {}
    try:
        me = _get("me", fields="user_id,username,account_type,media_count", ctx=ctx)
        checks["identity"] = {"ok": True, "username": me.get("username"),
                              "account_type": me.get("account_type"),
                              "media_count": me.get("media_count")}
        account_type = (me.get("account_type") or "").upper()
        if account_type not in {"BUSINESS", "MEDIA_CREATOR", "CREATOR"}:
            checks["account_type"] = {
                "ok": False,
                "detail": f"Tipe akun '{account_type or 'tidak diketahui'}' tidak bisa memakai Content Publishing API. "
                          "Ubah akun ke Business/Creator di aplikasi Instagram (Pengaturan > Akun > Beralih ke akun profesional).",
            }
        else:
            checks["account_type"] = {"ok": True, "detail": account_type}
    except Exception as exc:  # noqa: BLE001
        checks["identity"] = {"ok": False, "error": redact_text(str(exc))}

    try:
        limit = get_content_publishing_limit(ctx=ctx)
        checks["publishing_quota"] = {"ok": True, **limit}
    except Exception as exc:  # noqa: BLE001
        checks["publishing_quota"] = {"ok": False, "error": redact_text(str(exc))}

    try:
        media = _get(f"{config.need('IG_USER_ID')}/media",
                     fields="id,media_type,timestamp,permalink", limit=1, ctx=ctx)
        checks["read_access"] = {"ok": True, "sample_media": (media.get("data") or [None])[0]}
    except Exception as exc:  # noqa: BLE001
        checks["read_access"] = {"ok": False, "error": redact_text(str(exc))}

    healthy = all(v.get("ok") for v in checks.values())
    result.update(status="connected" if healthy else "degraded", checks=checks)
    if not healthy:
        result["hints"] = _diagnose(checks)
    return result


def _diagnose(checks: dict) -> list[str]:
    hints: list[str] = []
    identity = checks.get("identity") or {}
    account = checks.get("account_type") or {}
    quota = checks.get("publishing_quota") or {}
    if not identity.get("ok"):
        hints.append("Token Instagram tidak valid atau kedaluwarsa. Buat long-lived token baru di "
                     "Meta app > Instagram > API setup with Instagram login, lalu perbarui IG_TOKEN.")
    if account and not account.get("ok"):
        hints.append(account.get("detail", ""))
    if not quota.get("ok"):
        hints.append("Kuota publishing tidak bisa dibaca: pastikan scope instagram_business_content_publish "
                     "disetujui dan akun sudah terhubung ke Meta app.")
    elif quota.get("quota_usage") is not None and quota.get("config", {}).get("quota_total"):
        usage, total = quota["quota_usage"], quota["config"]["quota_total"]
        if usage >= total:
            hints.append(f"Kuota posting Instagram habis ({usage}/{total}) dalam 24 jam terakhir.")
    if not (checks.get("read_access") or {}).get("ok"):
        hints.append("Tidak bisa membaca media akun: periksa scope instagram_business_basic.")
    return [h for h in hints if h]
