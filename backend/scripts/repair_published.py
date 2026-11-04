"""Perbaiki data run yang posting Instagram-nya SUDAH terbit tetapi pencatatan lokalnya gagal.

Jalankan dari folder backend (tidak perlu restart backend; skema disinkronkan oleh skrip ini sendiri):
    python scripts/repair_published.py
Jika skema gagal dilonggarkan (skrip akan memberi tahu), pakai:
    python scripts/repair_published.py --force-recreate
yang HANYA menghapus tabel post_analytics (data turunan: dibuat ulang kosong lalu diisi ulang di bawah / lewat ingest).
Aman dijalankan berulang.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from src.core.db import (ContentStrategyItem, PostAnalytics, Publication, SessionLocal, engine,  # noqa: E402
                         ensure_schema, ingest_publication_metrics)


def reach_nullable() -> bool:
    return {c["name"]: c["nullable"] for c in inspect(engine).get_columns("post_analytics")}["reach"]


if "--force-recreate" in sys.argv:
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS post_analytics"))
    print("Tabel post_analytics dihapus; akan dibuat ulang.")

if inspect(engine).has_table("post_analytics"):
    print("post_analytics.reach nullable SEBELUM sinkron:", reach_nullable())
ensure_schema(engine)
ok = reach_nullable()
print("post_analytics.reach nullable SESUDAH sinkron:", ok)
if not ok:
    print("GAGAL melonggarkan skema. Jalankan ulang dengan --force-recreate.")
    sys.exit(1)

fixed_items = created_rows = 0
with SessionLocal() as s:
    for pub in s.query(Publication).filter_by(status="published").all():
        item = s.query(ContentStrategyItem).filter_by(run_id=pub.run_id).first() if pub.run_id else None
        if item and item.status in ("publishing", "publication_failed"):
            item.status = "published"
            fixed_items += 1
        if not s.query(PostAnalytics).filter_by(publication_id=pub.id).first():
            ingest_publication_metrics(s, pub, {"format": "carousel"}, source="instagram_api_pending_metrics")
            created_rows += 1
    s.commit()
print(f"Item kalender diperbaiki: {fixed_items}; baris analytics dibuat: {created_rows}")
