"""Programmatic Video Assembler using MoviePy and Pillow."""

import os
from pathlib import Path
from typing import List, Optional, Tuple
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
from src.video.models import SceneSpec, WordTiming
from src.video.subtitle_builder import (
    create_kinetic_subtitle_frame,
    create_headline_overlay_frame,
    create_branded_outro_frame,
    group_words_into_phrases,
    CANVAS_WIDTH,
    CANVAS_HEIGHT,
)

DEFAULT_FPS = 30


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

    # Fallback to dark corporate navy color
    return ColorClip(size=(canvas_w, canvas_h), color=(11, 42, 91), duration=duration_sec)


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


def assemble_single_scene(
    scene_spec: SceneSpec,
    broll_path: Optional[str],
    voiceover_path: str,
    word_timings: List[WordTiming],
    scene_duration_sec: float,
) -> CompositeVideoClip:
    """
    Assemble one scene: B-Roll background + Dark vignette + Headline overlay + Subtitles + Voiceover.
    If the scene role is 'cta' or outro, uses a dedicated Branded Outro Card layout.
    """
    is_outro = getattr(scene_spec, "role", "").lower() in ("cta", "outro")

    if is_outro:
        # Outro Scene: Use dedicated corporate brand card
        outro_frame = create_branded_outro_frame()
        outro_clip = (
            ImageClip(outro_frame, is_mask=False)
            .with_start(0)
            .with_duration(scene_duration_sec)
        )
        scene_comp = CompositeVideoClip([outro_clip], size=(CANVAS_WIDTH, CANVAS_HEIGHT))

        # Audio layer
        if os.path.exists(voiceover_path) and os.path.getsize(voiceover_path) > 100:
            audio_clip = AudioFileClip(voiceover_path)
            if audio_clip.duration < scene_duration_sec:
                scene_comp = scene_comp.with_duration(audio_clip.duration)
                scene_comp = scene_comp.with_audio(audio_clip)
            else:
                audio_clip = audio_clip.subclipped(0, scene_duration_sec)
                scene_comp = scene_comp.with_audio(audio_clip)

        return scene_comp

    # 1. Base video track
    base_clip = build_scene_video_track(broll_path, scene_duration_sec)

    # 2. Dark contrast overlay for readability (dark vignette / translucent black)
    vignette = ColorClip(
        size=(CANVAS_WIDTH, CANVAS_HEIGHT),
        color=(0, 0, 0),
        duration=scene_duration_sec,
    ).with_opacity(0.35)

    # 3. Top Headline card
    headline_frame = create_headline_overlay_frame(scene_spec.headline_overlay)
    headline_clip = (
        ImageClip(headline_frame, is_mask=False)
        .with_start(0)
        .with_duration(scene_duration_sec)
    )

    # 4. Animated Subtitle clips
    subtitle_clips = build_subtitle_clips(word_timings)

    # 5. Composite video layers
    all_layers = [base_clip, vignette, headline_clip] + subtitle_clips
    scene_comp = CompositeVideoClip(all_layers, size=(CANVAS_WIDTH, CANVAS_HEIGHT))

    # 6. Audio layer
    if os.path.exists(voiceover_path) and os.path.getsize(voiceover_path) > 100:
        audio_clip = AudioFileClip(voiceover_path)
        # Ensure audio duration does not cause bounds error
        if audio_clip.duration < scene_duration_sec:
            # Pad audio with silence or clamp scene duration
            scene_comp = scene_comp.with_duration(audio_clip.duration)
            scene_comp = scene_comp.with_audio(audio_clip)
        else:
            audio_clip = audio_clip.subclipped(0, scene_duration_sec)
            scene_comp = scene_comp.with_audio(audio_clip)

    return scene_comp


def assemble_full_video(
    scenes_data: List[dict],
    out_mp3_bgm_path: Optional[str] = None,
    out_video_path: str = "output/reels/final_reels.mp4",
    fps: int = DEFAULT_FPS,
) -> str:
    """
    Combine all assembled scenes sequentially and apply optional background music.
    
    scenes_data list of dicts:
        {
            "scene_spec": SceneSpec,
            "broll_path": str,
            "voiceover_path": str,
            "word_timings": [WordTiming],
            "duration_sec": float,
        }
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_video_path)), exist_ok=True)

    assembled_clips = []
    for item in scenes_data:
        clip = assemble_single_scene(
            scene_spec=item["scene_spec"],
            broll_path=item.get("broll_path"),
            voiceover_path=item["voiceover_path"],
            word_timings=item.get("word_timings", []),
            scene_duration_sec=item["duration_sec"],
        )
        assembled_clips.append(clip)

    final_video = concatenate_videoclips(assembled_clips, method="compose")

    # Background music mixing if provided
    if out_mp3_bgm_path and os.path.exists(out_mp3_bgm_path):
        try:
            bgm = AudioFileClip(out_mp3_bgm_path)
            # Loop bgm if shorter than video
            if bgm.duration < final_video.duration:
                bgm = afx.AudioLoop(bgm, duration=final_video.duration)
            else:
                bgm = bgm.subclipped(0, final_video.duration)

            # Ducking: soft 12% volume
            bgm = bgm.with_volume_scaled(0.12)
            if final_video.audio:
                combined_audio = CompositeAudioClip([final_video.audio, bgm])
                final_video = final_video.with_audio(combined_audio)
        except Exception:
            pass

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
