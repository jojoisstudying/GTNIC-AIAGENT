"""Programmatic Video Assembler using MoviePy and Pillow."""

import os
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple
import numpy as np

from moviepy import (
    VideoFileClip,
    ColorClip,
    ImageClip,
    AudioFileClip,
    CompositeVideoClip,
    CompositeAudioClip,
    concatenate_videoclips,
    vfx,
    afx,
)

from src import config
from src.reels.models import SceneSpec, WordTiming
from src.reels.tools.subtitle_builder import (
    create_kinetic_subtitle_frame,
    create_headline_overlay_frame,
    create_branded_outro_frame,
    get_palette,
    group_words_into_phrases,
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
)

DEFAULT_FPS = 30
TRANSITION_SEC = 0.25   # lama fade / crossfade antar scene
BGM_VOLUME = 0.14       # BGM di bawah suara (suara tetap dominan)
VALID_TRANSITIONS = ("fade", "crossfade", "none")


def build_scene_video_track(
    broll_path: Optional[str],
    duration_sec: float,
    canvas_w: int = CANVAS_WIDTH,
    canvas_h: int = CANVAS_HEIGHT,
) -> VideoFileClip | ColorClip:
    """
    Prepare background visual: resize/crop B-Roll to 1080x1920 or use solid dark brand background.
    """
    if broll_path and os.path.exists(broll_path) and os.path.getsize(broll_path) > 1000:
        try:
            clip = VideoFileClip(broll_path)
            # Loop video if shorter than needed duration
            if clip.duration < duration_sec:
                # Repeat or loop clip
                n_loops = int(np.ceil(duration_sec / clip.duration))
                clip = concatenate_videoclips([clip] * n_loops)

            clip = clip.subclipped(0, duration_sec)

            # Resize to fit portrait height or width
            w, h = clip.size
            scale = max(canvas_w / w, canvas_h / h)
            new_w, new_h = int(w * scale), int(h * scale)
            clip = clip.resized((new_w, new_h))

            # Center crop to 1080x1920
            x_center = new_w / 2
            y_center = new_h / 2
            clip = clip.cropped(
                x_center=x_center,
                y_center=y_center,
                width=canvas_w,
                height=canvas_h,
            )
            return clip
        except Exception:
            pass

    # Tanpa B-roll: latar warna utama brand (bukan navy hardcoded)
    return ColorClip(size=(canvas_w, canvas_h), color=get_palette()["primary"][:3], duration=duration_sec)


def build_subtitle_clips(
    words: List[WordTiming],
    canvas_w: int = CANVAS_WIDTH,
    canvas_h: int = CANVAS_HEIGHT,
) -> List[ImageClip]:
    """
    Create animated subtitle ImageClips synchronized with word timings.
    """
    phrases = group_words_into_phrases(words, max_words=4)
    subtitle_clips: List[ImageClip] = []

    for start_ms, end_ms, phrase_words in phrases:
        for idx, wt in enumerate(phrase_words):
            w_start_sec = max(0.0, wt.start_ms / 1000.0)
            if idx < len(phrase_words) - 1:
                next_start_sec = phrase_words[idx + 1].start_ms / 1000.0
                w_end_sec = max(w_start_sec + 0.15, next_start_sec)
            else:
                w_end_sec = max(w_start_sec + 0.35, wt.end_ms / 1000.0)
            w_dur = max(0.15, w_end_sec - w_start_sec)

            # Render single kinetic frame
            frame_rgba = create_kinetic_subtitle_frame(
                phrase_words=phrase_words,
                active_word_index=idx,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
            )

            # ImageClip in MoviePy
            clip = (
                ImageClip(frame_rgba, is_mask=False)
                .with_start(w_start_sec)
                .with_duration(w_dur)
            )
            subtitle_clips.append(clip)

    return subtitle_clips


def _attach_voiceover(scene_comp: CompositeVideoClip, voiceover_path: str,
                      scene_duration_sec: float) -> CompositeVideoClip:
    """Pasang voiceover. Durasi scene TIDAK dipotong mengikuti audio: sisa jeda (±0,3 detik dari
    pipeline) jadi napas antar scene dan ruang untuk crossfade tanpa menimpa suara."""
    if voiceover_path and os.path.exists(voiceover_path) and os.path.getsize(voiceover_path) > 100:
        audio_clip = AudioFileClip(voiceover_path)
        if audio_clip.duration > scene_duration_sec:
            audio_clip = audio_clip.subclipped(0, scene_duration_sec)
        scene_comp = scene_comp.with_audio(audio_clip)
    return scene_comp


def assemble_single_scene(
    scene_spec: SceneSpec,
    broll_path: Optional[str],
    voiceover_path: str,
    word_timings: List[WordTiming],
    scene_duration_sec: float,
    fade_in_sec: float = 0.0,
    fade_out_sec: float = 0.0,
) -> CompositeVideoClip:
    """
    Rakit satu scene: B-roll + peredam gelap + kartu atas + subtitle kinetik + voiceover.

    Kartu atas = headline untuk scene biasa, atau kartu CTA brand (logo, nama, kontak, tombol
    ajakan dari brand.json) untuk scene 'cta'/'outro'. Scene CTA kini memakai B-roll dan subtitle
    seperti scene lain, sehingga narasi CTA tetap terbaca.
    """
    is_cta = str(getattr(scene_spec, "role", "")).lower() in ("cta", "outro")

    # 1. Latar: B-roll (atau warna brand)
    base_clip = build_scene_video_track(broll_path, scene_duration_sec)

    # 2. Peredam gelap agar teks terbaca (scene CTA lebih gelap karena ada kartu padat)
    vignette = ColorClip(
        size=(CANVAS_WIDTH, CANVAS_HEIGHT),
        color=(0, 0, 0),
        duration=scene_duration_sec,
    ).with_opacity(0.55 if is_cta else 0.35)

    # 3. Kartu atas
    if is_cta:
        card_frame = create_branded_outro_frame(cta_text=scene_spec.headline_overlay)
    else:
        card_frame = create_headline_overlay_frame(scene_spec.headline_overlay)
    card_clip = (
        ImageClip(card_frame, is_mask=False)
        .with_start(0)
        .with_duration(scene_duration_sec)
    )

    # 4. Subtitle kinetik
    subtitle_clips = build_subtitle_clips(word_timings)

    # 5. Komposit + 6. audio
    scene_comp = CompositeVideoClip(
        [base_clip, vignette, card_clip] + subtitle_clips,
        size=(CANVAS_WIDTH, CANVAS_HEIGHT),
    )
    # 5b. Fade visual (transisi 'fade' = tenggelam ke hitam; suara tidak ikut berubah)
    fades = []
    if fade_in_sec > 0:
        fades.append(vfx.FadeIn(fade_in_sec))
    if fade_out_sec > 0:
        fades.append(vfx.FadeOut(fade_out_sec))
    if fades:
        scene_comp = scene_comp.with_effects(fades)

    return _attach_voiceover(scene_comp, voiceover_path, scene_duration_sec)


def _transition_of(spec: Any) -> str:
    t = str(getattr(spec, "transition", None) or "crossfade").lower()
    return t if t in VALID_TRANSITIONS else "crossfade"


def _mix_bgm(final_video, bgm_path: str, volume: float, warn: Callable[[str, dict], None]):
    """Campur BGM di bawah suara. Gagal apa pun -> video tetap jadi tanpa BGM, dan `warn` dipanggil
    (dulu semua error ditelan diam-diam)."""
    try:
        bgm = AudioFileClip(bgm_path)
        total = final_video.duration
        if bgm.duration < total:
            try:
                bgm = bgm.with_effects([afx.AudioLoop(duration=total)])
            except Exception as e:  # noqa: BLE001
                warn("video_bgm_loop_failed", {"error": f"{type(e).__name__}: {e}"})
        else:
            bgm = bgm.subclipped(0, total)
        bgm = bgm.with_volume_scaled(volume)
        try:
            bgm = bgm.with_effects([afx.AudioFadeIn(0.8), afx.AudioFadeOut(min(1.5, total / 3))])
        except Exception as e:  # noqa: BLE001 - tanpa fade masih bisa dipakai
            warn("video_bgm_fade_failed", {"error": f"{type(e).__name__}: {e}"})
        voice = final_video.audio
        mixed = CompositeAudioClip([voice, bgm]) if voice is not None else bgm
        return final_video.with_audio(mixed.with_duration(total))
    except Exception as e:  # noqa: BLE001
        warn("video_bgm_failed", {"error": f"{type(e).__name__}: {e}", "bgm": os.path.basename(str(bgm_path))})
        return final_video


def assemble_full_video(
    scenes_data: List[dict],
    out_mp3_bgm_path: Optional[str] = None,
    out_video_path: str = "output/reels/final_reels.mp4",
    fps: int = DEFAULT_FPS,
    bgm_volume: float = BGM_VOLUME,
    warn: Optional[Callable[[str, dict], None]] = None,
) -> str:
    """
    Gabungkan semua scene dengan transisi per scene, lalu campur BGM opsional.

    `SceneSpec.transition` = efek dari scene itu KE scene berikutnya:
      - "none"      : potong langsung
      - "fade"      : scene tenggelam ke hitam, scene berikutnya muncul dari hitam (scene terakhir
                      memudar di akhir video)
      - "crossfade" : scene berikutnya muncul perlahan di atas scene sebelumnya (tumpang-tindih
                      <= 0,25 detik, dan hanya sebesar jeda hening di akhir voiceover supaya
                      suara dua scene tidak pernah bertabrakan)

    scenes_data list of dicts:
        {"scene_spec": SceneSpec, "broll_path": str, "voiceover_path": str,
         "word_timings": [WordTiming], "duration_sec": float}
    """
    warn = warn or (lambda name, detail: None)
    os.makedirs(os.path.dirname(os.path.abspath(out_video_path)), exist_ok=True)

    transitions = [_transition_of(item["scene_spec"]) for item in scenes_data]

    assembled_clips = []
    for i, item in enumerate(scenes_data):
        clip = assemble_single_scene(
            scene_spec=item["scene_spec"],
            broll_path=item.get("broll_path"),
            voiceover_path=item["voiceover_path"],
            word_timings=item.get("word_timings", []),
            scene_duration_sec=item["duration_sec"],
            fade_in_sec=TRANSITION_SEC if i > 0 and transitions[i - 1] == "fade" else 0.0,
            fade_out_sec=TRANSITION_SEC if transitions[i] == "fade" else 0.0,
        )
        assembled_clips.append(clip)

    # Susun di timeline: scene i+1 mulai di akhir scene i, dimajukan sebesar overlap bila crossfade.
    layers, voice_tracks = [], []
    t = 0.0
    for i, clip in enumerate(assembled_clips):
        overlap = 0.0
        if i > 0 and transitions[i - 1] == "crossfade":
            prev = assembled_clips[i - 1]
            prev_audio = prev.audio.duration if prev.audio is not None else 0.0
            silent_tail = max(0.0, prev.duration - prev_audio)  # jeda hening setelah suara scene sebelumnya
            overlap = min(TRANSITION_SEC, silent_tail, 0.5 * prev.duration, 0.5 * clip.duration)
        start = max(0.0, t - overlap)

        visual = clip.without_audio()
        if overlap > 0:
            visual = visual.with_effects([vfx.CrossFadeIn(overlap)])
        layers.append(visual.with_start(start))
        if clip.audio is not None:
            voice_tracks.append(clip.audio.with_start(start))
        t = start + clip.duration

    final_video = CompositeVideoClip(layers, size=(CANVAS_WIDTH, CANVAS_HEIGHT)).with_duration(t)
    if voice_tracks:
        final_video = final_video.with_audio(CompositeAudioClip(voice_tracks).with_duration(t))

    if out_mp3_bgm_path and os.path.exists(out_mp3_bgm_path):
        final_video = _mix_bgm(final_video, out_mp3_bgm_path, bgm_volume, warn)

    # Write output MP4
    final_video.write_videofile(
        out_video_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",  # Fast rendering for local generation
        threads=4,
        logger=None,  # Silent logs
    )

    # Clean up MoviePy clips to free file handles
    final_video.close()
    for c in assembled_clips:
        c.close()

    return out_video_path
