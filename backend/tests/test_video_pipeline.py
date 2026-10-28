"""Integration tests for full video pipeline orchestrator."""

import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.reels.models import VideoScriptSchema, SceneSpec, WordTiming, VideoRunResult
from src.reels.pipeline import VideoPipeline


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
    with patch("src.reels.pipeline.generate_voiceover_with_subtitles", new_callable=AsyncMock) as mock_tts:
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
            bgm_resolver=None,  # tes ini tidak menguji BGM (lihat test_pipeline_dedupes_broll_and_mixes_bgm)
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


@pytest.mark.asyncio
async def test_pipeline_dedupes_broll_and_mixes_bgm(tmp_path):
    """E + #7: scene kedua tidak boleh memakai klip scene pertama; BGM dipilih dan dilaporkan."""
    import wave
    import numpy as np
    from types import SimpleNamespace
    from src.reels.tools.bgm import resolve_bgm_track

    out_mp4 = str(tmp_path / "final_bgm.mp4")
    scenes = [
        SceneSpec(scene_index=1, role="hook", narration="Apa bedanya HTTP dan HTTPS?",
                  search_keywords=["padlock browser"], headline_overlay="HTTP VS HTTPS", transition="crossfade"),
        SceneSpec(scene_index=2, role="cta", narration="Simpan video ini.",
                  search_keywords=["padlock browser"], headline_overlay="SIMPAN", transition="fade"),
    ]
    script = VideoScriptSchema(topic="HTTPS", target_duration_sec=15, bgm_mood="energetic_tech", scenes=scenes)
    sw = MagicMock()
    sw.generate_script.return_value = script

    clips = iter(["klip_a.mp4", "klip_b.mp4"])
    fetcher = MagicMock()
    fetcher.fetch_clip.side_effect = lambda kw, **k: next(clips)
    fetcher.last_info = {"source": "pexels", "query": "padlock browser", "reused": False}

    events = []
    ctx = SimpleNamespace(emit=lambda kind, name, **f: events.append((kind, name, f)))

    def fake_tts(text, out_path, voice=None, rate=None):
        with wave.open(out_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(np.zeros(22050, dtype=np.int16).tobytes())
        return out_path, [WordTiming(word="Test", start_ms=0, end_ms=500)], 1000

    with patch("src.reels.pipeline.generate_voiceover_with_subtitles", new_callable=AsyncMock) as tts:
        tts.side_effect = fake_tts
        vp = VideoPipeline(
            scriptwriter=sw, broll_fetcher=fetcher, context=ctx,
            bgm_resolver=lambda mood, dur: resolve_bgm_track(mood, dur, cache_dir=tmp_path / "bgm"),
        )
        result = await vp.run_pipeline(topic="HTTPS", out_video_path=out_mp4, out_dir=tmp_path)

    assert result.ok is True and os.path.exists(out_mp4)
    first, second = fetcher.fetch_clip.call_args_list
    assert first.kwargs["exclude"] == []
    assert second.kwargs["exclude"] == ["klip_a.mp4"]            # scene 2 diberi tahu klip scene 1

    names = [e[1] for e in events]
    assert names.count("video_broll_selected") == 2
    bgm_ev = [e for e in events if e[1] == "video_bgm_selected"]
    assert bgm_ev and bgm_ev[0][2]["detail"]["mood"] == "energetic_tech"
    assert bgm_ev[0][2]["detail"]["source"] == "synth"
    assert not [e for e in events if e[1].startswith("video_bgm_") and e[0] == "warning"]
