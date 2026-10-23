"""Masukkan foto cutout ASLI (PNG transparan) ke library.
Contoh: python -m scripts.add_asset data/assets/budi_mikir.png mikir "Budi sedang berpikir"
Foto asli otomatis diutamakan dibanding placeholder untuk tag yang sama."""
import sys
from src.tools import asset_library

path, tags = sys.argv[1], sys.argv[2].split(",")
asset_library.add_asset(path, tags, sys.argv[3] if len(sys.argv) > 3 else "")
print("Ditambahkan:", path, tags)