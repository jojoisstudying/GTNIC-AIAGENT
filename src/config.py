import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def need(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Env var {name} belum diisi di .env")
    return v


def opt(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def database_url() -> str:
    """Return the configured SQLAlchemy URL or the local ignored SQLite database."""
    return opt("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'app.db'}")
