"""Video Generation Pipeline Orchestrator and CLI Runner."""

import os
import sys
import time
import asyncio
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

from src import config
from src.core.context import RunContext
from src.video.models import VideoScriptSchema, VideoRunResult
from src.video.scriptwriter import VideoScriptwriter
from src.video.tts_engine import generate_voiceover_with_subtitles
from src.video.broll_fetcher import BRollFetcher
from src.video.compositor import assemble_full_video
from src.video.qc_video import verify_video_quality


class VideoPipeline:
    """End-to-end multi-agent pipeline for generating vertical Reels/Shorts videos."""

    def __init__(
        self,
        scriptwriter: Optional[VideoScriptwriter] = None,
        broll_fetcher: Optional[BRollFetcher] = None,
        context: Optional[RunContext] = None,
    ):
        self.scriptwriter = scriptwriter or VideoScriptwriter()
        self.broll_fetcher = broll_fetcher or BRollFetcher()
        self.ctx = context

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        if self.ctx and hasattr(self.ctx, "emit"):
            self.ctx.emit(event_type, data)

    async def run_pipeline(
        self,
        topic: str,
        research_context: Optional[str] = None,
        target_duration_sec: int = 30,
        out_video_path: Optional[str] = None,
        out_dir: Optional[Path] = None,
    ) -> VideoRunResult:
        """
        Execute full 5-stage pipeline:
        Stage 1: Scriptwriter Agent -> VideoScriptSchema
        Stage 2: TTS Generation & Word Timing
        Stage 3: B-Roll Fetching (Pexels / Cache)
        Stage 4: Programmatic Video Assembly (MoviePy)
        Stage 5: QC Guardrail Check
        """
        t0 = time.time()
        self._emit("video_pipeline_started", {"topic": topic, "target_duration_sec": target_duration_sec})

        output_dir = Path(out_dir or (config.ROOT / "output" / "reels"))
        output_dir.mkdir(parents=True, exist_ok=True)
        final_video_file = out_video_path or str(output_dir / f"reels_{int(time.time())}.mp4")

        # ---------------------------------------------------------------------
        # Stage 1: Scriptwriter Agent
        # ---------------------------------------------------------------------
        script = self.scriptwriter.generate_script(
            topic=topic,
            research_context=research_context,
            target_duration_sec=target_duration_sec,
        )
        self._emit("video_script_generated", {
            "scenes_count": len(script.scenes),
            "topic": script.topic,
        })

        # ---------------------------------------------------------------------
        # Stage 2 & 3: Audio TTS + B-Roll Fetching per Scene
        # ---------------------------------------------------------------------
        scenes_data = []
        for idx, scene in enumerate(script.scenes):
            scene_audio_path = str(output_dir / f"temp_scene_{idx + 1}.mp3")

            # Stage 2: TTS
            _, word_timings, total_ms = await generate_voiceover_with_subtitles(
                text=scene.narration,
                out_path=scene_audio_path,
            )
            # Duration in seconds (at least 2.0s)
            scene_dur_sec = max(2.0, (total_ms / 1000.0) + 0.3)

            # Stage 3: B-Roll
            broll_clip = self.broll_fetcher.fetch_clip(scene.search_keywords)

            scenes_data.append({
                "scene_spec": scene,
                "broll_path": broll_clip,
                "voiceover_path": scene_audio_path,
                "word_timings": word_timings,
                "duration_sec": scene_dur_sec,
            })

        # ---------------------------------------------------------------------
        # Stage 4: Video Compositor Assembly
        # ---------------------------------------------------------------------
        self._emit("video_assembly_started", {"scenes_count": len(scenes_data)})
        assembled_path = assemble_full_video(
            scenes_data=scenes_data,
            out_video_path=final_video_file,
            fps=30,
        )

        # Clean up temporary audio files
        for item in scenes_data:
            p = item.get("voiceover_path")
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        # ---------------------------------------------------------------------
        # Stage 5: QC Guardrail Check
        # ---------------------------------------------------------------------
        total_planned_sec = sum(item["duration_sec"] for item in scenes_data)
        qc_result = verify_video_quality(
            video_path=assembled_path,
            target_duration_sec=total_planned_sec,
            tolerance_sec=5.0,
            max_size_mb=50.0,
        )
        qc_result.scenes_count = len(scenes_data)

        elapsed = time.time() - t0
        self._emit("video_pipeline_finished", {
            "ok": qc_result.ok,
            "duration_sec": qc_result.duration_sec,
            "elapsed_pipeline_sec": round(elapsed, 2),
            "file_size_mb": qc_result.file_size_mb,
            "issues": qc_result.issues,
        })

        return qc_result


async def main_cli():
    """CLI entrypoint for running the video generator pipeline."""
    parser = argparse.ArgumentParser(description="Multi-Agent Video Reels Generator")
    parser.add_argument("--topic", type=str, required=True, help="Topic for the video reels")
    parser.add_argument("--duration", type=int, default=30, help="Target duration in seconds")
    parser.add_argument("--out", type=str, default=None, help="Output MP4 file path")
    args = parser.parse_args()

    print(f"🎬 Memulai pipeline video untuk topik: '{args.topic}'...")
    pipeline = VideoPipeline()
    result = await pipeline.run_pipeline(
        topic=args.topic,
        target_duration_sec=args.duration,
        out_video_path=args.out,
    )

    if result.ok:
        print("\n✅ VIDEO BERHASIL DIBUAT!")
        print(f"📍 File: {result.video_path}")
        print(f"⏱️ Durasi: {result.duration_sec:.1f} detik")
        print(f"📦 Ukuran File: {result.file_size_mb:.2f} MB")
        print(f"🎬 Jumlah Scene: {result.scenes_count}")
    else:
        print("\n❌ GAGAL QC:")
        for issue in result.issues:
            print(f"  - {issue}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main_cli())
