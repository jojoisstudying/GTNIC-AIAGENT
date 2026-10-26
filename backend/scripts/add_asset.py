"""Masukkan foto cutout ASLI (PNG transparan) ke library.
Contoh: python -m scripts.add_asset data/assets/budi_mikir.png mikir "Budi sedang berpikir"
Foto asli otomatis diutamakan dibanding placeholder untuk tag yang sama."""
import argparse
import sys
from src.tools import asset_library


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Masukkan foto cutout ASLI (PNG transparan) ke asset library."
    )
    parser.add_argument("path", help="Path ke file foto cutout PNG transparan")
    parser.add_argument("tags", help="Daftar tag dipisahkan koma (misal: mikir,senyum)")
    parser.add_argument("description", nargs="?", default="", help="Deskripsi opsional asset")

    args = parser.parse_args()
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    asset_library.add_asset(args.path, tags, args.description)
    print("Ditambahkan:", args.path, tags)
    return 0


if __name__ == "__main__":
    sys.exit(main())
