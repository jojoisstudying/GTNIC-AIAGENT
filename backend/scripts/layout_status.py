"""CLI status layout. DIJALANKAN MANUSIA (pemilik proyek), bukan agent.

  python scripts/layout_status.py list
  python scripts/layout_status.py approve <layout_id> [<layout_id> ...]
  python scripts/layout_status.py retire  <layout_id> ...
  python scripts/layout_status.py draft   <layout_id> ...
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.layouts import registry  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(__doc__)
        return 0
    cmd, ids = argv[0], argv[1:]
    if cmd == "list":
        specs = registry.load_all()
        for s in sorted(specs.values(), key=lambda x: (x.meta.batch, x.id)):
            print(f"batch {s.meta.batch}  {s.meta.status:9s} {s.meta.role:12s} {s.id}")
        counts: dict[str, int] = {}
        for s in specs.values():
            counts[s.meta.status] = counts.get(s.meta.status, 0) + 1
        print("ringkasan:", counts)
        return 0
    target = {"approve": "approved", "retire": "retired", "draft": "draft"}.get(cmd)
    if not target or not ids:
        print("Perintah tidak dikenal atau id kosong. Lihat --help.")
        return 2
    for layout_id in ids:
        registry.set_status(layout_id, target)
        print(f"{layout_id} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
