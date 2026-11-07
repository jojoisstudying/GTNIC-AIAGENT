"""Probe Cloudinary: cek konfigurasi + signature + upload nyata dengan respons mentah."""
import os
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src import config  # memuat .env
import requests
import cloudinary.utils

cn = config.opt("CLOUDINARY_CLOUD_NAME")
key = config.opt("CLOUDINARY_API_KEY")
secret = config.opt("CLOUDINARY_API_SECRET")
print("cloud_name:", repr(cn))
print("api_key len:", len(key), "secret len:", len(secret), "secret stripped-equal:", secret == secret.strip())

# sample images
samples = sorted(Path("output").rglob("*.png"))[:3] + sorted(Path("output").rglob("*.jpg"))[:3]
print("samples:", [str(p) for p in samples][:4])
if not samples:
    sys.exit("no sample image")

p = samples[0]
print("sample:", p, "size:", p.stat().st_size, "ext:", p.suffix)

params = {"folder": "gtnic-posters", "public_id": f"probe_{int(time.time())}",
          "timestamp": int(time.time()), "overwrite": "false"}
sig = cloudinary.utils.api_sign_request(params, secret)
print("signature:", sig)

url = f"https://api.cloudinary.com/v1_1/{cn}/image/upload"
resp = requests.post(url, data={**params, "api_key": key, "signature": sig},
                     files={"file": (p.name, p.read_bytes(), "image/jpeg")}, timeout=120)
print("HTTP:", resp.status_code)
print("HEADERS content-type:", resp.headers.get("content-type"))
body = resp.text[:2000]
print("RAW BODY:", body)
