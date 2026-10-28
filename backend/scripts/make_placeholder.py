"""Buat 6 foto PLACEHOLDER (siluet sederhana) agar poster bisa dites sebelum foto karyawan asli ada.
Jalankan: python -m scripts.make_placeholder"""
import json
from PIL import Image, ImageDraw
from src import config
from src.carousel.tools import asset_library

BODY, SKIN, DARK = (74, 132, 205, 255), (240, 200, 170, 255), (60, 70, 90, 255)


def figure(pose: str) -> Image.Image:
    im = Image.new("RGBA", (600, 900), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([160, 280, 440, 900], radius=70, fill=BODY)            # badan
    d.rectangle([265, 235, 335, 300], fill=SKIN)                               # leher
    d.ellipse([205, 80, 395, 270], fill=SKIN)                                  # kepala
    d.pieslice([205, 70, 395, 230], 180, 360, fill=(60, 45, 40, 255))          # rambut
    for x in (260, 340):
        d.ellipse([x - 8, 170, x + 8, 186], fill=DARK)                         # mata
    arm = lambda pts, w=52: (d.line(pts, fill=BODY, width=w, joint="curve"), d.ellipse(
        [pts[-1][0] - 30, pts[-1][1] - 30, pts[-1][0] + 30, pts[-1][1] + 30], fill=SKIN))
    if pose == "senyum":
        d.arc([255, 190, 345, 245], 20, 160, fill=DARK, width=6)
        arm([(180, 330), (140, 560), (150, 640)]); arm([(420, 330), (460, 560), (450, 640)])
    elif pose == "mikir":
        d.line([(265, 225), (335, 225)], fill=DARK, width=6)
        arm([(420, 330), (470, 470), (350, 270)]); arm([(180, 330), (150, 560), (230, 600)])
    elif pose == "menunjuk":
        d.arc([255, 190, 345, 245], 20, 160, fill=DARK, width=6)
        arm([(420, 330), (500, 300), (550, 270)]); arm([(180, 330), (140, 560), (150, 640)])
    elif pose == "pegang_laptop":
        d.arc([255, 190, 345, 245], 20, 160, fill=DARK, width=6)
        arm([(180, 330), (150, 520), (230, 640)]); arm([(420, 330), (450, 520), (370, 640)])
        d.rounded_rectangle([170, 560, 430, 700], radius=14, fill=(55, 60, 75, 255))
        d.polygon([(150, 700), (450, 700), (470, 735), (130, 735)], fill=(120, 125, 140, 255))
    elif pose == "pegang_tablet":
        d.arc([255, 190, 345, 245], 20, 160, fill=DARK, width=6)
        arm([(180, 330), (170, 500), (240, 600)]); arm([(420, 330), (430, 500), (360, 600)])
        d.rounded_rectangle([225, 470, 375, 690], radius=14, fill=(40, 45, 60, 255))
    elif pose == "tangan_disilang":
        d.arc([255, 190, 345, 245], 20, 160, fill=DARK, width=6)
        arm([(180, 340), (300, 500), (420, 470)], 56); arm([(420, 340), (300, 500), (180, 470)], 56)
    else:
        arm([(180, 330), (140, 560)]); arm([(420, 330), (460, 560)])
    return im


brand = json.loads((config.ROOT / "config" / "brand.json").read_text(encoding="utf-8"))
out = config.ROOT / "data" / "assets"
out.mkdir(parents=True, exist_ok=True)
for pose in brand.get("available_poses", []):
    p = out / f"placeholder_{pose}.png"
    figure(pose).save(p)
    asset_library.add_asset(str(p), [pose], f"PLACEHOLDER pose {pose}")
    print("dibuat:", p.name)