"""Unit tests for AI Video Scriptwriter agent."""

from unittest.mock import MagicMock
from src.video.scriptwriter import VideoScriptwriter
from src.video.models import VideoScriptSchema


def test_scriptwriter_mock_llm():
    mock_llm = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = """
    {
      "topic": "Strategi Cashflow",
      "target_duration_sec": 30,
      "bgm_mood": "corporate_minimal",
      "scenes": [
        {
          "scene_index": 1,
          "role": "hook",
          "narration": "Kenapa 80 persen startup gulung tikar?",
          "search_keywords": ["business failure"],
          "headline_overlay": "80% STARTUP GAGAL?",
          "transition": "fade"
        },
        {
          "scene_index": 2,
          "role": "cta",
          "narration": "Simpan video ini dan follow untuk tips selanjutnya.",
          "search_keywords": ["modern office"],
          "headline_overlay": "SIMPAN & FOLLOW",
          "transition": "none"
        }
      ]
    }
    """
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_llm.chat.return_value = mock_resp

    writer = VideoScriptwriter(llm_client=mock_llm)
    script = writer.generate_script(topic="Strategi Cashflow")

    assert isinstance(script, VideoScriptSchema)
    assert script.topic == "Strategi Cashflow"
    assert len(script.scenes) == 2
    assert script.scenes[0].role == "hook"


def test_scriptwriter_fallback_on_error():
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = RuntimeError("Groq API offline")

    writer = VideoScriptwriter(llm_client=mock_llm)
    script = writer.generate_script(topic="Manajemen Risiko Bisnis")

    assert isinstance(script, VideoScriptSchema)
    assert script.topic == "Manajemen Risiko Bisnis"
    assert len(script.scenes) == 4
    assert script.scenes[0].headline_overlay == "KESALAHAN FATAL"
    assert script.scenes[-1].role == "cta"
