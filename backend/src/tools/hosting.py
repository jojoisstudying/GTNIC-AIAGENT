"""Upload poster FINAL ke Cloudinary agar Meta punya URL publik. Jangan upload foto mentah karyawan.

Catatan penting soal error "Stale request":
Cloudinary memvalidasi `timestamp` pada request bertanda tangan dan menolak request yang
jamnya melenceng lebih dari 1 jam dari jam servernya. Nilai itu berasal dari jam
perangkat, sehingga server dengan jam salah akan gagal 100% walaupun kredensial benar.
Modul ini mendeteksi kondisi tersebut dari pesan error, mempelajari offset jam server,
lalu mengulang sekali dengan timestamp terkoreksi.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import requests

from src import config
from src.core.http import HttpClient, HttpError

log = logging.getLogger("gtnic.hosting")

IMAGE_MAX_MB = 30.0
VIDEO_MAX_MB = 100.0
IG_MIN_WIDTH = 320
IG_MAX_WIDTH = 1440
_STALE_RE = re.compile(r"reported time is ([\d-]+\s+[\d:]+\s*[+-]\d{4})", re.I)

# Offset jam perangkat vs jam server Cloudinary (detik). Dipelajari saat "Stale request".
_clock_offset_seconds: dict[str, int] = {}


class CloudinaryError(RuntimeError):
    """Kegagalan upload Cloudinary dengan konteks yang bisa ditindaklanjuti operator."""

    def __init__(self, message: str, *, status_code: int | None = None, hint: str | None = None) -> None:
        super().__init__(message + (f" — {hint}" if hint else ""))
        self.status_code = status_code
        self.hint = hint


def _credentials() -> tuple[str, str, str]:
    cloud_name = config.need("CLOUDINARY_CLOUD_NAME").strip()
    api_key = config.need("CLOUDINARY_API_KEY").strip()
    api_secret = config.need("CLOUDINARY_API_SECRET").strip()
    if any(ch.isspace() for ch in (cloud_name, api_key, api_secret)):
        raise CloudinaryError(
            "Kredensial Cloudinary mengandung spasi/baris baru.",
            hint="hapus spasi atau tanda kutip di CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET pada .env",
        )
    return cloud_name, api_key, api_secret


def clock_offset(cloud_name: str) -> int:
    """Offset (detik) yang harus ditambahkan ke jam perangkat agar sama dengan Cloudinary."""
    return _clock_offset_seconds.get(cloud_name, 0)


def _timestamp(cloud_name: str) -> int:
    return int(time.time()) + clock_offset(cloud_name)


def _learn_offset_from_error(cloud_name: str, message: str) -> bool:
    """Pelajari offset jam dari pesan 'Stale request'. True bila offset berhasil diperbarui."""
    match = _STALE_RE.search(message or "")
    if not match:
        return False
    raw = match.group(1).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            server_ts = datetime.strptime(raw, fmt).timestamp()
        except ValueError:
            continue
        offset = int(round(server_ts - time.time()))
        if abs(offset) > 30:
            _clock_offset_seconds[cloud_name] = offset
            log.warning(
                "Jam perangkat melenceng %+.1f jam dari Cloudinary; timestamp upload dikoreksi otomatis "
                "(sebaiknya tetap sinkronkan waktu server lewat NTP).", offset / 3600)
            return True
    return False


def _detect_mime(path: Path, default: str) -> str:
    """Tentukan MIME dari isi file, bukan dari nama file."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            fmt = (im.format or "").lower()
        return {"jpeg": "image/jpeg", "jpg": "image/jpeg", "png": "image/png",
                "webp": "image/webp"}.get(fmt, default)
    except Exception:  # noqa: BLE001 - video / file non-gambar
        return default


def _prepare_jpeg(path: str) -> bytes:
    """Pastikan isi file benar-benar JPEG berukuran wajar untuk Instagram.

    Instagram Content Publishing hanya menerima JPEG untuk gambar feed. Slide hasil
    renderer sudah JPEG; PNG/WEBP dikonversi di sini supaya tidak ditolak Meta.
    """
    from PIL import Image

    p = Path(path)
    if not p.is_file():
        raise CloudinaryError(f"File tidak ditemukan: {path}",
                              hint="jalankan ulang pembuatan konten; file slide hilang dari disk")
    size_mb = p.stat().st_size / (1024 * 1024)
    if size_mb > IMAGE_MAX_MB:
        raise CloudinaryError(f"Gambar terlalu besar ({size_mb:.1f} MB, batas {IMAGE_MAX_MB:.0f} MB)",
                              hint="kecilkan resolusi/kompresi slide sebelum dipublikasikan")
    raw = p.read_bytes()
    try:
        with Image.open(BytesIO(raw)) as im:
            im.load()
            fmt = (im.format or "").upper()
            width, height = im.size
            if fmt in {"JPEG", "JPG"} and width <= IG_MAX_WIDTH:
                return raw
            # Instagram feed optimal 1080 px lebar (min 320, maks 1440).
            target_w = 1080 if width > IG_MAX_WIDTH else max(width, IG_MIN_WIDTH)
            if target_w != width:
                ratio = target_w / float(width)
                im = im.resize((target_w, int(round(height * ratio))), Image.LANCZOS)
            buf = BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=92, optimize=True)
            log.info("Gambar %s dikonversi ke JPEG %dx%d untuk Instagram", p.name, *im.size)
            return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        raise CloudinaryError(f"Gambar tidak bisa dibaca: {p.name} ({type(exc).__name__})",
                              hint="file slide rusak; buat ulang konten") from exc


def _idempotent_public_id(path: str, folder: str) -> str:
    """public_id deterministik dari isi file: upload ulang tidak membuat duplikat.

    `folder` dikirim sebagai parameter terpisah Cloudinary, jadi public_id TIDAK
    boleh memuat folder lagi (dulu jadi "gtnic-posters/gtnic-posters/...").
    """
    p = Path(path)
    digest = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return f"{p.stem}_{digest}"


def _hint_for(status_code: int | None, message: str) -> str | None:
    text = (message or "").lower()
    if "stale request" in text:
        return ("jam server berbeda lebih dari 1 jam dari Cloudinary. Sinkronkan waktu server (NTP); "
                "timestamp upload kini dikoreksi otomatis")
    if status_code in (401, 403) or "invalid signature" in text or "unauthorized" in text:
        return ("periksa CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET di backend/.env — "
                "nilainya harus dari dashboard Cloudinary akun yang sama")
    if status_code == 420 or "rate" in text:
        return "kuota/laju Cloudinary terlampaui; coba lagi beberapa saat lagi"
    if "invalid image file" in text or "invalid file" in text:
        return "file gambar rusak/format tidak dikenal; buat ulang slide"
    if status_code == 413 or "too large" in text:
        return "file melebihi batas ukuran paket Cloudinary Anda"
    return None


def _signed_upload(*, endpoint: str, path: str, folder: str, mime: str, max_mb: float,
                   timeout: int, http: HttpClient | None,
                   payload: bytes | None = None) -> dict:
    """Upload bertanda tangan ke Cloudinary, dengan koreksi jam + satu kali retry."""
    import cloudinary.utils

    cloud_name, api_key, api_secret = _credentials()
    data_bytes = payload if payload is not None else Path(path).read_bytes()
    if len(data_bytes) / (1024 * 1024) > max_mb:
        raise CloudinaryError(f"File melebihi batas {max_mb:.0f} MB Cloudinary sinkron",
                              hint="kompres file atau gunakan paket Cloudinary yang lebih besar")

    public_id = _idempotent_public_id(path, folder)
    url = f"https://api.cloudinary.com/v1_1/{cloud_name}/{endpoint}"
    last_error: Exception | None = None

    for attempt in (1, 2):
        params = {"folder": folder, "public_id": public_id, "timestamp": _timestamp(cloud_name),
                  "overwrite": "false"}
        signature = cloudinary.utils.api_sign_request(params, api_secret)
        form = {**params, "api_key": api_key, "signature": signature}
        files = {"file": (Path(path).name, data_bytes, mime)}
        try:
            if http:
                response = http.request("POST", url, step="publisher", provider="cloudinary",
                                        timeout=timeout, data=form, files=files)
                res = response.json()
            else:
                res = requests.post(url, data=form, files=files, timeout=timeout).json()
        except HttpError as exc:
            last_error = exc
            if attempt == 1 and _learn_offset_from_error(cloud_name, str(exc)):
                continue  # ulangi sekali dengan timestamp terkoreksi
            raise CloudinaryError(
                f"Upload ke Cloudinary gagal (HTTP {exc.status_code}): {exc.provider_message or exc}",
                status_code=exc.status_code, hint=_hint_for(exc.status_code, str(exc))) from None
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            raise CloudinaryError(f"Upload ke Cloudinary gagal: {type(exc).__name__}: {exc}") from None

        if isinstance(res, dict) and res.get("error"):
            message = res["error"].get("message") if isinstance(res["error"], dict) else str(res["error"])
            raise CloudinaryError(f"Cloudinary menolak upload: {message}",
                                  hint=_hint_for(None, str(message)))
        if isinstance(res, dict) and res.get("secure_url"):
            return res
        raise CloudinaryError(f"Cloudinary tidak mengembalikan secure_url: {str(res)[:300]}")

    raise CloudinaryError(f"Upload ke Cloudinary gagal setelah percobaan ulang: {last_error}")


def upload_jpeg(path: str, folder: str = "gtnic-posters", *, http: HttpClient | None = None) -> str:
    """Upload gambar (dipaksa JPEG) dan kembalikan URL publik langsung ke file .jpg."""
    payload = _prepare_jpeg(path)
    res = _signed_upload(endpoint="image/upload", path=path, folder=folder, mime="image/jpeg",
                         max_mb=IMAGE_MAX_MB, timeout=120, http=http, payload=payload)
    url = str(res["secure_url"])
    if not url.split("?")[0].lower().endswith((".jpg", ".jpeg")):
        # Instagram menolak URL non-JPEG: minta Cloudinary mengonversi saat file diakses.
        head, _, tail = url.partition("/upload/")
        if tail:
            url = f"{head}/upload/f_jpg,q_auto/{tail}"
    log.info("Cloudinary: %s terunggah (%s bytes) -> %s", Path(path).name, res.get("bytes"),
             url.split("?")[0])
    return url


def upload_video(path: str, folder: str = "gtnic-reels", *, http: HttpClient | None = None) -> str:
    """Upload video FINAL (MP4/MOV) agar Meta punya URL publik langsung ke file video.

    Batas upload sinkron Cloudinary ~100 MB (paket gratis); video Reels kita jauh di bawah itu,
    dan `publisher.preflight_video` menolak file yang terlalu besar sebelum sampai sini.
    """
    p = Path(path)
    if not p.is_file():
        raise CloudinaryError(f"File tidak ditemukan: {path}",
                              hint="jalankan ulang pembuatan video; file hilang dari disk")
    size_mb = p.stat().st_size / (1024 * 1024)
    if size_mb > VIDEO_MAX_MB:
        raise CloudinaryError(f"Video terlalu besar ({size_mb:.1f} MB, batas {VIDEO_MAX_MB:.0f} MB)")
    res = _signed_upload(endpoint="video/upload", path=path, folder=folder,
                         mime=_detect_mime(p, "video/mp4"), max_mb=VIDEO_MAX_MB, timeout=300,
                         http=http)
    url = str(res["secure_url"])
    base = url.split("?")[0]
    if not base.lower().endswith((".mp4", ".mov")):
        stem = base.rsplit(".", 1)[0] if "." in base.rsplit("/", 1)[-1] else base
        url = stem + ".mp4"
    log.info("Cloudinary: %s terunggah (%s bytes) -> %s", p.name, res.get("bytes"), url.split("?")[0])
    return url
