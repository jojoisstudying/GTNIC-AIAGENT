"""One-shot worker for the isolated rembg/Pillow environment.

Input and output are raw PNG/JPEG bytes on stdin/stdout. Invoke only from trusted
server code with REMBG_PYTHON pointing at the optional image-processing environment.
"""
import sys

from rembg import new_session, remove


def main() -> None:
    source = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
    if len(source) > 10 * 1024 * 1024:
        raise ValueError("input image exceeds 10 MiB")
    session = new_session("u2net")
    sys.stdout.buffer.write(remove(source, session=session))


if __name__ == "__main__":
    main()
