"""Asset library retrieve-first; images and SQLite metadata stay under ignored data/."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import sqlite3
from src import config

DB = config.ROOT / "data" / "app.db"


def _conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY, path TEXT UNIQUE, tags TEXT, description TEXT,
        status TEXT NOT NULL DEFAULT 'approved', person_id TEXT, source_path TEXT,
        model TEXT, prompt TEXT, cache_key TEXT UNIQUE, created_at TEXT
    )""")
    columns = {row[1] for row in c.execute("PRAGMA table_info(assets)")}
    migrations = {
        "status": "TEXT NOT NULL DEFAULT 'approved'", "person_id": "TEXT",
        "source_path": "TEXT", "model": "TEXT", "prompt": "TEXT",
        "cache_key": "TEXT", "created_at": "TEXT",
    }
    for name, declaration in migrations.items():
        if name not in columns:
            c.execute(f"ALTER TABLE assets ADD COLUMN {name} {declaration}")
    columns = {row[1] for row in c.execute("PRAGMA table_info(assets)")}
    extra_migrations = {"run_id": "TEXT", "sha256": "TEXT", "kind": "TEXT"}
    for name, declaration in extra_migrations.items():
        if name not in columns:
            c.execute(f"ALTER TABLE assets ADD COLUMN {name} {declaration}")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_assets_cache_key ON assets(cache_key) WHERE cache_key IS NOT NULL")
    return c


def add_asset(path: str, tags: list[str], description: str = "", *, status: str = "approved",
              person_id: str | None = None, source_path: str | None = None,
              model: str | None = None, prompt: str | None = None,
              cache_key: str | None = None, run_id: str | None = None,
              kind: str | None = None) -> int:
    if status not in {"pending_review", "approved", "rejected", "placeholder"}:
        raise ValueError(f"Status asset tidak dikenal: {status}")
    created_at = datetime.now(timezone.utc).isoformat()
    asset_path = Path(path)
    digest = hashlib.sha256(asset_path.read_bytes()).hexdigest() if asset_path.is_file() else None
    with _conn() as c:
        c.execute("""INSERT INTO assets(path,tags,description,status,person_id,source_path,model,prompt,cache_key,created_at,run_id,sha256,kind)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(path) DO UPDATE SET tags=excluded.tags, description=excluded.description,
                       status=excluded.status, person_id=excluded.person_id, source_path=excluded.source_path,
                       model=excluded.model, prompt=excluded.prompt, cache_key=excluded.cache_key,
                       run_id=COALESCE(excluded.run_id, assets.run_id), sha256=excluded.sha256,
                       kind=COALESCE(excluded.kind, assets.kind)""",
                  (str(path), ",".join(t.strip().lower() for t in tags), description, status,
                   person_id, source_path, model, prompt, cache_key, created_at, run_id, digest, kind))
        row = c.execute("SELECT id FROM assets WHERE path=?", (str(path),)).fetchone()
    return int(row[0])


def list_assets(status: str | None = None) -> list[dict]:
    with _conn() as c:
        select_columns = "id,path,tags,description,status,person_id,source_path,model,prompt,cache_key,created_at,run_id,sha256,kind"
        if status:
            rows = c.execute(f"SELECT {select_columns} FROM assets WHERE status=? ORDER BY id", (status,)).fetchall()
        else:
            rows = c.execute(f"SELECT {select_columns} FROM assets ORDER BY id").fetchall()
    keys = ("id", "path", "tags", "description", "status", "person_id", "source_path", "model", "prompt", "cache_key", "created_at", "run_id", "sha256", "kind")
    return [dict(zip(keys, (r[0], r[1], r[2].split(","), *r[3:]))) for r in rows]


def find_cached(cache_key: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT id,path,tags,description,status,person_id,source_path,model,prompt,cache_key,created_at,run_id,sha256,kind FROM assets WHERE cache_key=?", (cache_key,)).fetchone()
    if not row:
        return None
    keys = ("id", "path", "tags", "description", "status", "person_id", "source_path", "model", "prompt", "cache_key", "created_at", "run_id", "sha256", "kind")
    return dict(zip(keys, (row[0], row[1], row[2].split(","), *row[3:])))


def set_status(asset_selector: int | str, status: str) -> int:
    if status not in {"approved", "rejected"}:
        raise ValueError("Review hanya boleh mengubah status menjadi approved atau rejected")
    selector = str(asset_selector).strip()
    with _conn() as c:
        if selector.isdecimal():
            rows = c.execute("SELECT id FROM assets WHERE id=? AND status='pending_review'", (int(selector),)).fetchall()
        elif re.fullmatch(r"[a-fA-F0-9]{8,64}", selector):
            rows = c.execute("SELECT id FROM assets WHERE cache_key LIKE ? AND status='pending_review'", (selector + "%",)).fetchall()
            if len(rows) > 1:
                raise LookupError(f"Prefix cache key '{selector}' cocok dengan beberapa asset; gunakan key lengkap dari list_assets")
        else:
            raise ValueError("Masukkan ID numerik database atau prefix hexadecimal cache key")
        if not rows:
            raise LookupError(f"Asset pendente '{selector}' não encontrado. Rode: python -m scripts.list_assets")
        asset_id = int(rows[0][0])
        c.execute("UPDATE assets SET status=? WHERE id=? AND status='pending_review'", (status, asset_id))
    return asset_id


def get_asset(asset_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT id,path,tags,description,status,person_id,source_path,model,prompt,cache_key,created_at,run_id,sha256,kind FROM assets WHERE id=?", (asset_id,)).fetchone()
    if not row:
        return None
    keys = ("id", "path", "tags", "description", "status", "person_id", "source_path", "model", "prompt", "cache_key", "created_at", "run_id", "sha256", "kind")
    return dict(zip(keys, (row[0], row[1], row[2].split(","), *row[3:])))


def pending_assets() -> list[dict]:
    return list_assets(status="pending_review")


def get_person_reference(person_id: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", person_id):
        raise ValueError("person_id may contain only letters, numbers, underscore, and hyphen")
    people_dir = config.ROOT / "data" / "people"
    matches = [p for p in people_dir.glob(f"{person_id}/reference.*") if p.is_file()]
    return str(matches[0]) if matches else None


def is_placeholder(path: str | None) -> bool:
    return bool(path) and "placeholder" in str(path).lower()


def is_cutout(path: str | None) -> bool:
    """True only for an existing PNG asset whose alpha channel has transparency."""
    if not path or Path(path).suffix.lower() != ".png" or not Path(path).is_file():
        return False
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.mode in {"RGBA", "LA"} and image.getchannel("A").getextrema()[0] < 255
    except Exception:
        return False


def find_pose(wanted_tags: list[str]) -> str | None:
    """Pick the best approved match, prioritizing real cutouts over opaque photos/placeholders."""
    wanted = {t.strip().lower() for t in wanted_tags or []}
    best, best_key = None, (0, 0, 0, "")
    for a in list_assets(status="approved"):
        overlap = len(wanted & set(a["tags"]))
        if overlap == 0:
            continue
        key = (
            overlap,
            1 if is_cutout(a["path"]) else 0,
            0 if is_placeholder(a["path"]) else 1,
            a.get("created_at") or "",
        )
        if key > best_key:
            best, best_key = a["path"], key
    return best


def find_opaque_generated_pose(wanted_tags: list[str]) -> dict | None:
    """Return newest approved generated opaque photo matching requested tags."""
    wanted = {t.strip().lower() for t in wanted_tags or []}
    matches = [
        asset for asset in list_assets(status="approved")
        if len(wanted.intersection(asset["tags"])) == len(wanted) and wanted
        and asset.get("model")
        and Path(asset["path"]).is_file()
        and not is_cutout(asset["path"])
        and not is_placeholder(asset["path"])
    ]
    return max(matches, key=lambda asset: asset.get("created_at") or "", default=None)