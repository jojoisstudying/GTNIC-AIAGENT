"""List local photo assets and their review state."""
from src.carousel.tools import asset_library

for asset in asset_library.list_assets():
    key = f" | cache {asset['cache_key'][:16]}" if asset.get("cache_key") else ""
    print(f"DB ID {asset['id']} | {asset['status']:13} | {','.join(asset['tags'])}{key} | {asset['path']}")
