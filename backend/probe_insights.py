"""Probe insight per-media: metrik apa yang benar-benar didukung/ditolak Meta."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src import config
import requests

base = config.opt("IG_API_BASE", "https://graph.instagram.com")
token = config.opt("IG_TOKEN")
uid = config.opt("IG_USER_ID")

media = requests.get(f"{base}/{uid}/media", params={
    "fields": "id,caption,media_type,timestamp,permalink,like_count,comments_count", "limit": 3,
    "access_token": token}, timeout=30).json()["data"]

for m in media:
    print(f"\n=== {m['id']} type={m['media_type']} likes={m.get('like_count')} comments={m.get('comments_count')}")
    print("   basic fields single:", requests.get(f"{base}/{m['id']}", params={
        "fields": "id,like_count,comments_count,timestamp,permalink,media_type,media_product_type",
        "access_token": token}, timeout=30).status_code,
        requests.get(f"{base}/{m['id']}", params={
        "fields": "id,like_count,comments_count,timestamp,permalink,media_type,media_product_type",
        "access_token": token}, timeout=30).text[:300])

    for metric in ("reach", "saved", "shares", "views", "total_interactions", "profile_visits", "follows",
                   "impressions", "plays", "engagement", "likes", "comments"):
        r = requests.get(f"{base}/{m['id']}/insights", params={"metric": metric, "access_token": token}, timeout=30)
        body = r.text.replace("\n", " ")[:150]
        print(f"   {metric:18} {r.status_code} {body}")
    # gabungan
    r = requests.get(f"{base}/{m['id']}/insights", params={
        "metric": "reach,saved,shares,views,total_interactions", "access_token": token}, timeout=30)
    print("   combined:", r.status_code, r.text[:400])
