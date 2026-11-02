"""Backup database SQLite (API + asset library) memakai SQLite online-backup API (aman saat server berjalan).

Pemakaian (dari folder backend):  python scripts/backup_db.py [--dest backups] [--keep 7]
Jalankan lewat cron, mis. harian:  0 2 * * * cd /app/backend && python scripts/backup_db.py
Untuk PostgreSQL gunakan pg_dump; file media di data/ perlu dicadangkan terpisah (rsync/object storage).
"""
import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _targets() -> list[Path]:
    from src.core.db import engine
    from src.carousel.tools import asset_library
    paths = []
    if engine.url.get_backend_name() == "sqlite" and engine.url.database:
        paths.append(Path(engine.url.database))
    paths.append(Path(asset_library.DB))
    return [p for p in dict.fromkeys(paths) if p.is_file()]


def backup(dest: Path, keep: int) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    stamp, made = datetime.now().strftime("%Y%m%d-%H%M%S"), []
    for src in _targets():
        out = dest / f"{src.stem}-{stamp}{src.suffix or '.db'}"
        with sqlite3.connect(src) as a, sqlite3.connect(out) as b:
            a.backup(b)
        made.append(out)
        olds = sorted(dest.glob(f"{src.stem}-*{src.suffix or '.db'}"))
        for old in olds[:-keep]:
            old.unlink()
    return made


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="backups")
    ap.add_argument("--keep", type=int, default=7)
    args = ap.parse_args()
    files = backup(Path(args.dest), max(1, args.keep))
    print("\n".join(f"OK {f}" for f in files) or "Tidak ada database SQLite untuk dibackup.")
