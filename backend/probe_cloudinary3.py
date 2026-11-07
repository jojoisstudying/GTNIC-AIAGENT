"""Probe mode kegagalan Cloudinary: duplikat public_id, signature salah, file rusak, ukuran."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from src import config
import requests
import cloudinary.utils
from email.utils import parsedate_to_datetime

cn = config.opt("CLOUDINARY_CLOUD_NAME")
key = config.opt("CLOUDINARY_API_KEY")
secret = config.opt("CLOUDINARY_API_SECRET")
srv = requests.get(f"https://api.cloudinary.com/v1_1/{cn}/ping", timeout=20)
now_ts = int(parsedate_to_datetime(srv.headers["Date"]).timestamp())
base = f"https://api.cloudinary.com/v1_1/{cn}"
p = sorted(Path("output").rglob("*.jpg"))[0]

def go(label, params, data_extra=None, files=None, secret_override=None, url=f"{base}/image/upload"):
    params = {**params, "timestamp": now_ts}
    sig = cloudinary.utils.api_sign_request(params, secret_override or secret)
    r = requests.post(url, data={**params, "api_key": key, "signature": sig, **(data_extra or {})},
                      files=files, timeout=120)
    print(f"[{label}] HTTP {r.status_code}: {r.text[:400]}")
    return r

pid = f"gtnic-posters/dup_{now_ts}"
f = {"file": ("a.jpg", p.read_bytes(), "image/jpeg")}
go("first", {"public_id": pid, "overwrite": "false"}, files=f)
go("second-same-publicid", {"public_id": pid, "overwrite": "false"}, files=f)
go("bad-signature", {"public_id": pid + "x", "overwrite": "false"},
   files={"file": ("a.jpg", p.read_bytes(), "image/jpeg")}, secret_override="wrongsecret")
go("corrupt-file", {"public_id": pid + "_corrupt", "overwrite": "false"},
   files={"file": ("bad.jpg", b"\xff\xd8\xff\xe0not-an-image" * 100, "image/jpeg")})
