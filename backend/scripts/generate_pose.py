"""Generate one cached pose variant; new assets always require explicit review."""
import argparse

from src.carousel.tools.cloudflare_pose_generator import generate_pose


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("person_id")
    parser.add_argument("pose", help="Existing brand pose tag")
    parser.add_argument("--prompt", default="", help="Optional custom pose description")
    parser.add_argument("--force", action="store_true", help="Generate a new version even if cached")
    args = parser.parse_args()
    asset = generate_pose(args.person_id, args.pose, args.prompt, force=args.force)
    print(f"Database ID: {asset['id']} | status: {asset['status']} | cached: {asset.get('cached', False)}")
    print(f"Image: {asset['path']}")
    print(f"Cache key prefix: {asset.get('cache_key', '')[:16]}")
    if asset["status"] == "pending_review":
        print(f"Review the image, then run: python -m scripts.approve_asset {asset['id']}")


if __name__ == "__main__":
    main()
