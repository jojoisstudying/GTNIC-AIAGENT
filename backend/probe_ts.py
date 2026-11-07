"""Tes: signed upload tanpa parameter timestamp (menghindari masalah jam perangkat)."""
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

for label, params in [
    ("no-timestamp", {"folder": "gtnic-posters", "public_id": f"probe_nots_{int(time.time())}"}),
    ("with-timestamp", {"folder": "gtnic-posters", "public_id": f"probe_ts_{int(time.time())}",
                        "timestamp": int(time.time())}),
]:
    sig = cloudinary.utils.api_sign_request(params, secret)
    r = requests.post(f"{base}/image/upload", data={**params, "api_key": key, "signature": sig},
                      files={"file": (p.name, data, "image/jpeg")}, timeout=120)
    print(label, r.status_code, r.text[:200].replace("\n", " "))
