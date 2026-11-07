"""Probe lanjutan: upload dengan timestamp terkoreksi + berbagai resource/mime untuk cari akar 500."""
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src import config
import requests
import cloudinary.utils

cn = config.opt("CLOUDINARY_CLOUD_NAME")
key = config.opt("CLOUDINARY_API_KEY")
secret = config.opt("CLOUDINARY_API_SECRET")

# Koreksi jam: Cloudinary menolak timestamp > 1 jam beda. Ambil waktu server dari header Date.
srv = requests.get(f"https://api.cloudinary.com/v1_1/{cn}/ping", timeout=20)
from email.utils import parsedate_to_datetime
server_epoch = parsedate_to_datetime(srv.headers["Date"]).timestamp()
offset = int(server_epoch - time.time())
print(f"offset jam perangkat vs Cloudinary: {offset}s ({offset/3600:.2f} jam)")
now_ts = int(time.time()) + offset

samples = sorted(Path("output").rglob("*.jpg"))
p = samples[0]
print("sample:", p, p.stat().st_size)

def attempt(label, **kw):
    params = {"folder": "gtnic-posters", "public_id": f"probe_{label}_{now_ts}",
              "timestamp": now_ts, "overwrite": "false"}
    sig = cloudinary.utils.api_sign_request(params, secret)
    files = kw.pop("files")
    url = kw.pop("url")
    r = requests.post(url, data={**params, "api_key": key, "signature": sig}, files=files, timeout=180, **kw)
    print(f"\n[{label}] {url} -> HTTP {r.status_code}")
    print("  ", r.text[:600].replace("\n", " "))
    return r

base = f"https://api.cloudinary.com/v1_1/{cn}"
attempt("image-jpeg-mime", url=f"{base}/image/upload",
        files={"file": (p.name, p.read_bytes(), "image/jpeg")})
attempt("image-auto-mime", url=f"{base}/image/upload",
        files={"file": (p.name, p.read_bytes())})
attempt("auto-endpoint", url=f"{base}/auto/upload",
        files={"file": (p.name, p.read_bytes())})

# PNG diberi label jpeg (skenario lain)
pngs = sorted(Path("output").rglob("*.png"))
if pngs:
    q = pngs[0]
    attempt("png-as-jpeg", url=f"{base}/image/upload",
            files={"file": (q.name, q.read_bytes(), "image/jpeg")})
