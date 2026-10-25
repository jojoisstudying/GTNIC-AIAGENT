"""AI Scriptwriter Agent: transforms research facts & topics into high-converting video storyboards."""

import json
from typing import Dict, Any, Optional
from pydantic import ValidationError

from src.core.llm import LLMClient
from src.video.models import VideoScriptSchema, SceneSpec

SCRIPTWRITER_SYSTEM_PROMPT = """Kamu adalah Executive Social Media Video Producer & Copywriter untuk akun edukasi bisnis, teknologi, dan enterprise.
Tugasmu: Mengubah topik atau fakta riset menjadi naskah storyboard video Reels/Shorts vertikal (durasi 20–35 detik, 3–4 scene).

ATURAN UTAMA:
1. "Zero AI Slop": Gaya bahasa natural, tajam, profesional, berbasis fakta nyata. Hindari pembukaan klise seperti "Tahukah Anda" atau "Halo guys".
2. Hook Kuat (Scene 1): Pertanyaan tajam, counter-intuitive insight, atau angka statistik mengagetkan (maks 10-15 kata).
3. Struktur Scene:
   - Scene 1: hook (menghentikan scroll penonton)
   - Scene 2: problem atau explanation (akar masalah yang jarang disadari)
   - Scene 3: solution (solusi konkrit atau framework actionable)
   - Scene 4: cta (ajakan native sosial media: simpan video, follow akun, atau tulis komen)
4. Keywords B-Roll: Berikan 1-3 kata kunci berbahasa Inggris yang sangat visual dan spesifik untuk dicari di stock footage (contoh: "stressed businessman meeting", "financial data analytics", "smartphone notification").
5. Headline Overlay: Judul kartu teks pendek HURUF KAPITAL (2-4 kata, contoh: "80% STARTUP GAGAL?", "SOLUSI DUAL ACCOUNT").

Kamu WAJIB mengembalikan output dalam format JSON yang mematuhi skema VideoScriptSchema secara persis. Dilarang menyertakan teks pengantar di luar JSON."""


class VideoScriptwriter:
    """Agent that creates structured video scripts and storyboard from research facts."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    def generate_script(
        self,
        topic: str,
        research_context: Optional[str] = None,
        target_duration_sec: int = 30,
    ) -> VideoScriptSchema:
        """
        Calls LLM with strict JSON schema format to generate VideoScriptSchema.
        Fallback to a rule-based enterprise storyboard if LLM output fails validation.
        """
        user_prompt = f"TOPIK: {topic}\nTARGET DURASI: {target_duration_sec} detik"
        if research_context:
            user_prompt += f"\n\nFAKTA & HASIL RISET:\n{research_context}"

        messages = [
            {"role": "system", "content": SCRIPTWRITER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            resp = self.llm.chat(
                messages=messages,
                step="video_scriptwriter",
                response_format={"type": "json_object"},
            )
            raw_content = resp.choices[0].message.content or "{}"
            data = json.loads(raw_content)
            # Ensure topic and duration are present
            data.setdefault("topic", topic)
            data.setdefault("target_duration_sec", target_duration_sec)
            return VideoScriptSchema.model_validate(data)
        except Exception:
            # Deterministic, high-quality fallback storyboard
            return self._build_fallback_script(topic, target_duration_sec)

    def _build_fallback_script(
        self, topic: str, target_duration_sec: int
    ) -> VideoScriptSchema:
        """Fallback script when LLM is unavailable or unparseable."""
        return VideoScriptSchema(
            topic=topic,
            target_duration_sec=target_duration_sec,
            bgm_mood="corporate_minimal",
            scenes=[
                SceneSpec(
                    scene_index=1,
                    role="hook",
                    narration=f"Banyak bisnis terjebak kesalahan fatal saat menangani {topic}.",
                    search_keywords=["business failure meeting", "stressed office team"],
                    headline_overlay="KESALAHAN FATAL",
                    transition="fade",
                ),
                SceneSpec(
                    scene_index=2,
                    role="problem",
                    narration="Masalah utamanya bukan pada modal, melainkan strategi eksekusi yang tidak terukur.",
                    search_keywords=["finance charts falling", "calculator accounting"],
                    headline_overlay="EKSEKUSI TIDAK TERUKUR",
                    transition="crossfade",
                ),
                SceneSpec(
                    scene_index=3,
                    role="solution",
                    narration="Gunakan audit berkala dan otomatisasi alur kerja agar sistem berjalan otonom.",
                    search_keywords=["modern analytics dashboard", "success growth"],
                    headline_overlay="SOLUSI OTOMASI",
                    transition="crossfade",
                ),
                SceneSpec(
                    scene_index=4,
                    role="cta",
                    narration="Simpan video ini dan follow untuk strategi enterprise 2026.",
                    search_keywords=["modern enterprise tower", "smartphone notification"],
                    headline_overlay="SIMPAN & FOLLOW",
                    transition="fade",
                ),
            ],
        )
