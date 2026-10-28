"""Unit tests for subtitle and kinetic typography builder."""

import numpy as np
from src.reels.models import WordTiming
from src.reels.tools.subtitle_builder import (
    group_words_into_phrases,
    create_kinetic_subtitle_frame,
    create_headline_overlay_frame,
    hex_to_rgba,
    load_brand_tokens,
)


def test_hex_to_rgba():
    rgba = hex_to_rgba("#FFB400", alpha=200)
    assert rgba == (255, 180, 0, 200)

    # Fallback default
    assert hex_to_rgba("invalid") == (255, 255, 255, 255)


def test_load_brand_tokens():
    tokens = load_brand_tokens()
    assert isinstance(tokens, dict)
    assert "bg" in tokens or "accent" in tokens


def test_group_words_into_phrases():
    words = [
        WordTiming(word="Kenapa", start_ms=0, end_ms=300),
        WordTiming(word="80%", start_ms=300, end_ms=600),
        WordTiming(word="startup", start_ms=600, end_ms=1000),
        WordTiming(word="gagal?", start_ms=1000, end_ms=1500),
        WordTiming(word="Bukan", start_ms=1500, end_ms=1800),
        WordTiming(word="karena", start_ms=1800, end_ms=2100),
    ]
    phrases = group_words_into_phrases(words, max_words=4)
    # The first 4 words have punctuation 'gagal?' -> triggers phrase split
    assert len(phrases) == 2
    assert phrases[0][0] == 0
    assert phrases[0][1] == 1500
    assert len(phrases[0][2]) == 4
    assert len(phrases[1][2]) == 2


def test_group_words_empty():
    assert group_words_into_phrases([]) == []


def test_create_kinetic_subtitle_frame():
    words = [
        WordTiming(word="80%", start_ms=0, end_ms=300),
        WordTiming(word="Startup", start_ms=300, end_ms=600),
        WordTiming(word="Gagal", start_ms=600, end_ms=1000),
    ]
    # Active word is index 1 ("Startup")
    frame = create_kinetic_subtitle_frame(words, active_word_index=1)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (1920, 1080, 4)
    # Ensure there is non-transparent pixel content drawn
    assert frame[:, :, 3].max() > 0


def test_create_headline_overlay_frame():
    frame = create_headline_overlay_frame("80% STARTUP GAGAL?")
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (1920, 1080, 4)
    assert frame[:, :, 3].max() > 0


# ----------------------------------------------------------------------------
# Regresi: bug import (D), glitch badge subtitle (B), kartu CTA brand (C)
# ----------------------------------------------------------------------------
import typing

from src.reels.tools import subtitle_builder as sb

PHRASE = ["Bisa", "saat", "membuka", "situs"]


def _words(texts):
    return [WordTiming(word=t, start_ms=i * 300, end_ms=i * 300 + 300) for i, t in enumerate(texts)]


def _opaque_bbox(frame, mask=None):
    mask = (frame[:, :, 3] > 0) if mask is None else mask
    ys, xs = np.where(mask)
    return xs.min(), ys.min(), xs.max(), ys.max()


def test_type_hints_resolve_on_old_python():
    """D: Dict/Any dulu tidak di-import -> NameError saat import di Python < 3.14."""
    hints = typing.get_type_hints(sb.create_branded_outro_frame)
    assert "brand_config" in hints


def test_word_gap_is_wider_than_badge_padding():
    """B: jarak antarkata harus lebih lebar dari padding badge kiri+kanan."""
    L = sb.layout_subtitle_phrase(PHRASE)
    assert L["gap"] >= 2 * L["pad_x"] + 4


def test_active_badge_is_aligned_and_never_touches_neighbours():
    """B: badge sejajar dengan teks, tinggi konsisten, dan tidak menimpa kata tetangga."""
    pal = sb.get_palette()
    ar, ag, ab, _ = pal["accent"]
    L = sb.layout_subtitle_phrase(PHRASE)
    heights = set()
    for i in range(len(PHRASE)):
        frame = sb.create_kinetic_subtitle_frame(_words(PHRASE), i)
        badge = (frame[:, :, 0] == ar) & (frame[:, :, 1] == ag) & (frame[:, :, 2] == ab) & (frame[:, :, 3] == 255)
        x0, y0, x1, y1 = _opaque_bbox(frame, badge)
        heights.add((y0, y1))
        # badge hanya selebar kata aktif + padding
        assert x0 >= L["xs"][i] - L["pad_x"] - 1
        assert x1 <= L["xs"][i] + L["widths"][i] + L["pad_x"] + 1
        # dan tidak menyentuh teks tetangga
        if i + 1 < len(PHRASE):
            assert L["xs"][i + 1] - x1 >= 4
        if i > 0:
            assert x0 - (L["xs"][i - 1] + L["widths"][i - 1]) >= 4
    assert len(heights) == 1  # tinggi & posisi vertikal badge sama untuk semua kata


def test_subtitle_stays_inside_safe_margins_even_for_long_words():
    long_words = _words(["Infrastruktur", "keamanan", "digitalisasi", "berkelanjutan"])
    frame = sb.create_kinetic_subtitle_frame(long_words, 2)
    x0, _, x1, _ = _opaque_bbox(frame)
    assert x0 >= sb.SIDE_MARGIN and x1 <= CANVAS_W - sb.SIDE_MARGIN


CANVAS_W = 1080


def test_long_headline_fits_inside_margins_on_at_most_two_lines():
    frame = sb.create_headline_overlay_frame("Eksekusi tidak terukur pada seluruh tahapan proyek digital")
    x0, y0, x1, y1 = _opaque_bbox(frame)
    assert x0 >= sb.SIDE_MARGIN and x1 <= CANVAS_W - sb.SIDE_MARGIN
    assert y0 == sb.HEADLINE_Y and y1 < sb.HEADLINE_Y + 260


def test_accent_text_color_picks_readable_contrast():
    blue = sb.get_palette({"colors": {"primary": "#0f172a", "accent": "#1a5fb4"}})
    yellow = sb.get_palette({"colors": {"primary": "#0f172a", "accent": "#FFB400"}})
    assert blue["accent_fg"][:3] == (255, 255, 255)      # aksen gelap -> teks putih
    assert sum(yellow["accent_fg"][:3]) < 300             # aksen terang -> teks gelap


def test_outro_card_uses_brand_colors_and_stays_in_safe_area():
    """C: warna dari brand, teks panjang tidak terpotong, ada ruang untuk subtitle."""
    brand = {
        "company": "Resilience Digital Solutions International Group",
        "industry": "Pengembangan web & mobile app, desain UI/UX, audit sistem keamanan, integrasi API, "
                    "dan pemasaran digital untuk bisnis kecil dan menengah di seluruh Indonesia",
        "colors": {"primary": "#1a5fb4", "accent": "#f5c211"},
        "chrome": {"footer": {"show": True, "lines": ["@gtnic_resilience_official_account", "089716782567"]}},
    }
    frame = sb.create_branded_outro_frame(brand, cta_text="Simpan video ini dan bagikan ke temanmu")
    assert frame.shape == (1920, 1080, 4)
    assert frame[0, 0, 3] == 0  # transparan: B-roll tetap terlihat di luar kartu
    x0, y0, x1, y1 = _opaque_bbox(frame)
    assert 0 < x0 and x1 < CANVAS_W and x0 >= 80 and x1 <= CANVAS_W - 80
    assert y1 < sb.SUBTITLE_Y - 16  # tidak menabrak area subtitle

    # warna panel = warna utama brand (digelapkan sedikit), bukan navy hardcoded
    expected = sb._shade(sb.hex_to_rgba("#1a5fb4"), 0.92)[:3]
    assert tuple(int(v) for v in frame[y0 + 12, CANVAS_W // 2 - 380, :3]) == expected


def test_outro_card_opaque_background_option():
    frame = sb.create_branded_outro_frame({"colors": {"primary": "#112233", "accent": "#ffaa00"}},
                                          opaque_background=True)
    assert tuple(frame[5, 5]) == (0x11, 0x22, 0x33, 255)


def test_outro_card_without_logo_falls_back_to_initial_letter():
    frame = sb.create_branded_outro_frame({"company": "Zeta", "logo_path": "tidak/ada.png",
                                           "colors": {"primary": "#0f172a", "accent": "#10b981"}})
    assert frame[:, :, 3].max() > 0
