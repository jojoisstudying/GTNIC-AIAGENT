"""Renderer HTML -> JPG (Playwright/Chromium). Offline: semua request jaringan diblokir.

Selain gambar, renderer mengembalikan laporan DOM (bbox, font akhir, overflow) dan
kontras terukur dari piksel latar (glyph disembunyikan lalu dipotret ulang).
"""
from __future__ import annotations

import io
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import Browser, Playwright, sync_playwright

CANVAS_W, CANVAS_H = 1080, 1350
_BLOCKED = ("http://", "https://", "ws://", "wss://", "ftp://")
_HIDE_GLYPHS = "*{color:transparent!important;text-shadow:none!important;-webkit-text-stroke:0!important}"


class RenderError(RuntimeError):
    pass


@dataclass
class RenderResult:
    path: Path
    report: list[dict]
    blocked: list[str] = field(default_factory=list)
    ms: int = 0


def _parse_color(css: str) -> tuple[float, float, float, float]:
    nums = re.findall(r"[\d.]+", css)
    if len(nums) < 3:
        raise RenderError(f"warna tidak terbaca: {css!r}")
    r, g, b = (float(x) for x in nums[:3])
    return r, g, b, float(nums[3]) if len(nums) > 3 else 1.0


def _lum(rgb: np.ndarray) -> np.ndarray:
    c = rgb / 255.0
    lin = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def _measure_contrast(png: bytes, report: list[dict]) -> None:
    """Isi item['contrast_min'] = persentil-5 kontras terburuk di antara run teks."""
    arr = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
    for item in report:
        worst = None
        for run in item.get("runs", []):
            band_y0 = run["y"] + run["h"] * 0.3
            band_y1 = run["y"] + run["h"] * 0.7
            x0, x1 = max(0, int(run["x"])), min(CANVAS_W, int(run["x"] + run["w"]))
            y0, y1 = max(0, int(band_y0)), min(CANVAS_H, int(band_y1))
            if x1 - x0 < 2 or y1 - y0 < 1:
                continue
            px = arr[y0:y1:2, x0:x1:3].reshape(-1, 3).astype(float)
            r, g, b, a = _parse_color(run["color"])
            if a < 1.0:
                med = np.median(px, axis=0)
                r, g, b = (a * np.array([r, g, b]) + (1 - a) * med)
            lt = float(_lum(np.array([[r, g, b]]))[0])
            lb = _lum(px)
            ratios = (np.maximum(lb, lt) + 0.05) / (np.minimum(lb, lt) + 0.05)
            val = float(np.percentile(ratios, 5))
            worst = val if worst is None else min(worst, val)
        item["contrast_min"] = worst
        item.pop("runs", None)


class Renderer:
    """Pakai sebagai context manager agar browser dipakai ulang antar render."""

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

    def __enter__(self) -> "Renderer":
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(args=["--no-sandbox", "--font-render-hinting=none"])
        except Exception as exc:  # noqa: BLE001 - dibungkus dengan pesan yang jelas, lalu di-raise
            self._pw.stop()
            raise RenderError(f"Chromium gagal dijalankan (sudah 'playwright install chromium'?): {exc}") from exc
        return self

    def __exit__(self, *exc) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def render(self, html: str, out_path: str | Path, *, quality: int = 92) -> RenderResult:
        if not self._browser:
            raise RenderError("Renderer belum dibuka; pakai 'with Renderer() as r'")
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        blocked: list[str] = []
        context = self._browser.new_context(viewport={"width": CANVAS_W, "height": CANVAS_H}, device_scale_factor=1)

        def guard(route) -> None:
            url = route.request.url
            if url.startswith(_BLOCKED):
                blocked.append(url)
                route.abort()
            else:
                route.continue_()

        context.route("**/*", guard)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                page_file = Path(tmp) / "slide.html"
                page_file.write_text(html, encoding="utf-8")
                page = context.new_page()
                page.goto(page_file.as_uri(), wait_until="load")
                report = page.evaluate("window.__run()")
                page.screenshot(path=str(out), type="jpeg", quality=quality)
                page.add_style_tag(content=_HIDE_GLYPHS)
                png = page.screenshot(type="png")
        except Exception as exc:  # noqa: BLE001
            raise RenderError(f"render gagal untuk {out.name}: {exc}") from exc
        finally:
            context.close()
        _measure_contrast(png, report)
        return RenderResult(path=out, report=report, blocked=blocked, ms=int((time.perf_counter() - t0) * 1000))


def render_html(html: str, out_path: str | Path, *, quality: int = 92) -> RenderResult:
    with Renderer() as r:
        return r.render(html, out_path, quality=quality)
