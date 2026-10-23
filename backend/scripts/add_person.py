"""Register a consenting person's reference photo locally (never commits it)."""
import argparse
import re
import shutil
from pathlib import Path

from PIL import Image
from src import config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("person_id", help="Stable ID such as operator_01; avoid full legal names")
    parser.add_argument("photo", help="Reference photo path")
    parser.add_argument("--consent-confirmed", action="store_true",
                        help="Confirm the person agreed to AI editing and Cloudflare processing")
    args = parser.parse_args()
    if not args.consent_confirmed:
        parser.error("Need --consent-confirmed: confirm permission for AI editing and Cloudflare processing")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.person_id):
        parser.error("person_id may contain only letters, numbers, underscore, and hyphen")
    source = Path(args.photo).expanduser().resolve()
    if not source.is_file():
        parser.error(f"Photo not found: {source}")
    try:
        with Image.open(source) as image:
            image.verify()
    except Exception as exc:
        parser.error(f"Not a readable image: {exc}")
    person_dir = config.ROOT / "data" / "people" / args.person_id
    person_dir.mkdir(parents=True, exist_ok=True)
    target = person_dir / f"reference{source.suffix.lower()}"
    shutil.copy2(source, target)
    print(f"Reference saved locally: {target}")
    print("When generation is enabled, this photo is sent to Cloudflare Workers AI for pose editing.")


if __name__ == "__main__":
    main()
