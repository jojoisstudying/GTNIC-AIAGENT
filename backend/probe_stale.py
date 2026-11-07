"""Isolasi pemicu 'Stale request': variasi parameter signed."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from src import config
import requests, cloudinary.utils

cn = config.opt("CLOUDINARY_CLOUD_NAME"); key = config.opt("CLOUDINARY_API_KEY")
secret = config.opt("CLOUDINARY_API_SECRET")
base = f"https://api.cloudinary.com/v1_1/{cn}"
p = sorted(Path("output").rglob("*.jpg"))[0]
data = p.read_bytes()
ts = int(time.time())  # jam perangkat: 7 jam di belakang server

cases = {
    "plain": {"folder": "gtnic-posters", "public_id": f"iso_{ts}_a", "timestamp": ts},
    "overwrite-false": {"folder": "gtnic-posters", "public_id": f"iso_{ts}_b", "timestamp": ts, "overwrite": "false"},
    "overwrite-False-python": {"folder": "gtnic-posters", "public_id": f"iso_{ts}_c", "timestamp": ts, "overwrite": False},
    "overwrite-str-True": {"folder": "gtnic-posters", "public_id": f"iso_{ts}_d", "timestamp": ts, "overwrite": "true"},
}
for label, params in cases.items():
    sig = cloudinary.utils.api_sign_request(params, secret)
    payload = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in params.items()}
    r = requests.post(f"{base}/image/upload", data={**payload, "api_key": key, "signature": sig},
                      files={"file": ("a.jpg", data, "image/jpeg")}, timeout=120)
    print(f"{label:26} {r.status_code} {r.text[:140]}")

# ulangi plain dengan public_id sama 2x (cek overwrite)
for i in range(2):
    params = {"folder": "gtnic-posters", "public_id": f"iso_{ts}_dup", "timestamp": ts, "overwrite": "false"}
    sig = cloudinary.utils.api_sign_request(params, secret)
    r = requests.post(f"{base}/image/upload", data={**params, "api_key": key, "signature": sig},
                      files={"file": ("a.jpg", data, "image/jpeg")}, timeout=120)
    print(f"dup-run-{i}                  {r.status_code} {r.text[:140]}")
