"""Integration tests for full video pipeline orchestrator."""

import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.video.models import VideoScriptSchema, SceneSpec, WordTiming, VideoRunResult
from src.video.pipeline import VideoPipeline


@pytest.mark.asyncio
async def test_video_pipeline_orchestrator(tmp_path):
    out_mp4 = str(tmp_path / "final_test.mp4")

    # Mock Scriptwriter
    mock_scriptwriter = MagicMock()
    mock_scriptwriter.generate_script.return_value = VideoScriptSchema(
        topic="Startup Cashflow",
        target_duration_sec=20,
        scenes=[
            SceneSpec(
                scene_index=1,
                role="hook",
                narration="Kenapa 80 persen startup gagal?",
                search_keywords=["business failure"],
                headline_overlay="80% STARTUP GAGAL?",
            ),
            SceneSpec(
                scene_index=2,
                role="cta",
                narration="Follow kami sekarang.",
                search_keywords=["office"],
                headline_overlay="FOLLOW SEKARANG",
            ),
        ]
    )

    # Mock BRollFetcher
    mock_fetcher = MagicMock()
    mock_fetcher.fetch_clip.return_value = None  # Uses solid color background

    # Mock TTS to avoid live network latency during fast pytest
    with patch("src.video.pipeline.generate_voiceover_with_subtitles", new_callable=AsyncMock) as mock_tts:
        # Create a tiny wav for valid moviepy reading
        import wave, numpy as np
        def side_effect_tts(text, out_path, voice=None, rate=None):
            with wave.open(out_path, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(22050)
                wav.writeframes(np.zeros(22050, dtype=np.int16).tobytes())
            return out_path, [WordTiming(word="Test", start_ms=0, end_ms=500)], 1000

        mock_tts.side_effect = side_effect_tts

        pipeline = VideoPipeline(
            scriptwriter=mock_scriptwriter,
            broll_fetcher=mock_fetcher,
        )

        result = await pipeline.run_pipeline(
            topic="Startup Cashflow",
            out_video_path=out_mp4,
            out_dir=tmp_path,
        )

        assert isinstance(result, VideoRunResult)
        assert result.ok is True
        assert os.path.exists(out_mp4)
        assert result.scenes_count == 2
