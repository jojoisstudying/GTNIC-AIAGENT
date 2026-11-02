"""Lihat performa post terakhir (loop feedback): python -m scripts.run_metrics"""
from src.tools import instagram

r = instagram.get_my_recent_performance()
if r.get("error"):
    raise SystemExit(f"Gagal: {r['error']}")
print(f"{r['post_count']} post terbaca (cukup untuk kesimpulan: {r['enough_data']})")
for p in r["posts"]:
    print(f"- {p['timestamp'][:16]} | like {p.get('like_count')} | komentar {p.get('comments_count')} | {p.get('caption', '')[:50]!r}")