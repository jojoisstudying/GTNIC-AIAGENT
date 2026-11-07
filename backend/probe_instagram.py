"""Probe koneksi Instagram Graph API: identitas akun, tipe akun, izin, kuota."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src import config
import requests

base = config.opt("IG_API_BASE", "https://graph.instagram.com")
token = config.opt("IG_TOKEN")
uid = config.opt("IG_USER_ID")
print("base:", base)
print("token prefix:", token[:12], "len:", len(token))
print("IG_USER_ID:", repr(uid), "len:", len(uid), "all digits:", uid.isdigit())

print("\n--- /me ---")
r = requests.get(f"{base}/me", params={"fields": "user_id,username,account_type,media_count", "access_token": token}, timeout=30)
print(r.status_code, r.text[:800])

print("\n--- /{uid} ---")
r = requests.get(f"{base}/{uid}", params={"fields": "id,username,account_type,media_count,followers_count", "access_token": token}, timeout=30)
print(r.status_code, r.text[:800])

print("\n--- publishing limit ---")
r = requests.get(f"{base}/{uid}/content_publishing_limit", params={"fields": "quota_usage,config", "access_token": token}, timeout=30)
print(r.status_code, r.text[:800])

print("\n--- recent media ---")
r = requests.get(f"{base}/{uid}/media", params={"fields": "id,caption,timestamp,media_type,permalink,like_count,comments_count", "limit": 5, "access_token": token}, timeout=30)
print(r.status_code, r.text[:1200])
