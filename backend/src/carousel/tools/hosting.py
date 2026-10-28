"""Upload poster FINAL ke Cloudinary agar Meta punya URL publik. Jangan upload foto mentah karyawan."""
import time
from pathlib import Path
from src import config
from src.core.http import HttpClient


def upload_jpeg(path: str, folder: str = "gtnic-posters", *, http: HttpClient | None = None) -> str:
    import cloudinary  # lazy import
    import cloudinary.uploader
    import cloudinary.utils

    cloud_name = config.need("CLOUDINARY_CLOUD_NAME")
    api_key = config.need("CLOUDINARY_API_KEY")
    api_secret = config.need("CLOUDINARY_API_SECRET")
    public_id = f"{Path(path).stem}_{int(time.time())}"
    upload_params = {"folder": folder, "public_id": public_id, "timestamp": int(time.time()),
                     "overwrite": "false"}
    if http:
        signature = cloudinary.utils.api_sign_request(upload_params, api_secret)
        response = http.request(
            "POST", f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload",
            step="publisher", provider="cloudinary", timeout=120,
            data={**upload_params, "api_key": api_key, "signature": signature},
            files={"file": (Path(path).name, Path(path).read_bytes(), "image/jpeg")},
        )
        res = response.json()
    else:
        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
        res = cloudinary.uploader.upload(str(path), folder=folder, public_id=public_id,
                                         resource_type="image", overwrite=False)
    url = res["secure_url"]
    base = url.split("?")[0]
    if not base.lower().endswith((".jpg", ".jpeg")):   # Instagram butuh link langsung ke JPEG
        url = base.rsplit(".", 1)[0] + ".jpg"
    return url


def upload_video(path: str, folder: str = "gtnic-reels", *, http: HttpClient | None = None) -> str:
    """Upload file video MP4 ke Cloudinary agar Meta punya URL publik untuk publish Reels."""
    import cloudinary
    import cloudinary.uploader
    import cloudinary.utils

    cloud_name = config.need("CLOUDINARY_CLOUD_NAME")
    api_key = config.need("CLOUDINARY_API_KEY")
    api_secret = config.need("CLOUDINARY_API_SECRET")
    public_id = f"{Path(path).stem}_{int(time.time())}"
    upload_params = {
        "folder": folder,
        "public_id": public_id,
        "timestamp": int(time.time()),
        "overwrite": "false",
        "resource_type": "video",
    }
    if http:
        signature = cloudinary.utils.api_sign_request(upload_params, api_secret)
        response = http.request(
            "POST", f"https://api.cloudinary.com/v1_1/{cloud_name}/video/upload",
            step="publisher", provider="cloudinary", timeout=300,
            data={**upload_params, "api_key": api_key, "signature": signature},
            files={"file": (Path(path).name, Path(path).read_bytes(), "video/mp4")},
        )
        res = response.json()
    else:
        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
        res = cloudinary.uploader.upload(
            str(path), folder=folder, public_id=public_id,
            resource_type="video", overwrite=False
        )
    return res["secure_url"]