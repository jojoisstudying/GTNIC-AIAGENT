"""Reproduksi lewat kode produksi: hosting.upload_jpeg / upload_video dengan HttpClient."""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.core.http import HttpClient
from src.tools import hosting
from src.core.events import EventEmitter
from src.core.db import SessionLocal
from src.tools import hosting

http = HttpClient(emitter=EventEmitter(None, SessionLocal, printer=lambda s: print("  " + s)))

for pat in ("*.jpg", "*.png"):
    for p in sorted(Path("output").rglob(pat))[:2]:
        print(f"\n=== {p} ({p.stat().st_size} bytes) ===")
        try:
            url = hosting.upload_jpeg(str(p), http=http)
            print("  OK ->", url)
        except Exception as exc:
            print("  FAIL:", type(exc).__name__, exc)
