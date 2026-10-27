"""AI Scriptwriter Agent: mengubah topik + riset menjadi storyboard video vertikal.

Perilaku penting (sebelumnya semua ini hilang dan error ditelan diam-diam):
- Prompt memuat bentuk JSON yang diharapkan (nama field + nilai enum) dan anggaran kata
  yang dihitung dari durasi target.
- Output dinormalisasi (nama field/enum yang meleset), lalu divalidasi isinya
  (peran scene, anggaran kata, angka yang tidak ada di riset, keyword B-roll generik).
- Jika gagal, LLM diberi tahu persis apa yang salah dan diminta memperbaiki (maks MAX_ATTEMPTS).
- Jika tetap gagal: raise ScriptGenerationError. TIDAK ada naskah fallback generik, karena
  naskah bohongan membuat setiap video terlihat sama dan tidak relevan dengan topik.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from pydantic import ValidationError

from src.core.llm import LLMClient
from src.video.models import VideoScriptSchema

# Diukur dari run nyata: 41 kata -> 18,1 detik suara (id-ID-ArdiNeural, rate +5%).
WORDS_PER_SEC = 2.2
SCENE_PAD_SEC = 0.3  # VideoPipeline menambah 0.3 detik per scene
MAX_ATTEMPTS = 3

ALLOWED_ROLES = ("hook", "problem", "explanation", "solution", "cta")
ALLOWED_MOODS = ("corporate_minimal", "energetic_tech", "inspiring_ambient", "dramatic_urgent")
ALLOWED_TRANSITIONS = ("fade", "crossfade", "none")

ROLE_ALIASES = {
    "intro": "hook", "opening": "hook", "hook": "hook",
    "problem": "problem", "masalah": "problem",
    "explanation": "explanation", "explain": "explanation", "body": "explanation",
    "penjelasan": "explanation", "insight": "explanation",
    "solution": "solution", "solusi": "solution",
    "cta": "cta", "outro": "cta", "closing": "cta", "call_to_action": "cta",
    "call-to-action": "cta", "call to action": "cta",
}

# Keyword stock footage yang terlalu umum: membuat semua video terlihat sama.
GENERIC_KEYWORDS = {
    "business meeting", "office team", "team meeting", "success", "businessman", "business",
    "office", "teamwork", "meeting", "business failure meeting", "stressed office team",
    "people working", "corporate", "business team",
}

BANNED_OPENERS = re.compile(r"^\s*(tahukah anda|tahukah kamu|halo guys|hai guys|halo semua|hai semua)", re.I)

SYSTEM_PROMPT = """Kamu adalah Video Producer & Copywriter untuk akun edukasi bisnis dan teknologi.
Tugasmu: mengubah TOPIK (dan RISET bila ada) menjadi naskah storyboard video Reels vertikal.

ATURAN ISI:
1. Jelaskan topik itu sendiri secara akurat. Jangan mengulang topik mentah di narasi seperti template ("kesalahan fatal saat menangani <topik>").
2. Gaya lisan Indonesia yang natural dan profesional. Kalimat pendek (maks 14 kata). Tanpa pembukaan klise ("Tahukah Anda", "Halo guys").
3. Scene pertama = hook (pertanyaan tajam / fakta mengejutkan, maks 15 kata). Scene terakhir = cta (ajakan native: simpan, bagikan, atau komentar). Scene di antaranya: problem / explanation / solution.
4. KEJUJURAN: hanya tulis klaim yang ada di RISET. Jika RISET kosong, pakai pengetahuan umum yang mapan saja. DILARANG membuat angka, persentase, atau statistik yang tidak tertulis di RISET.
5. search_keywords: 1-3 kata kunci BAHASA INGGRIS yang konkret, visual, dan berhubungan langsung dengan isi scene dan topik (contoh: "padlock browser address bar", "server room cables"). DILARANG keyword generik seperti "business meeting", "office team", "success".
6. headline_overlay: 2-4 kata, HURUF KAPITAL, merangkum scene.
7. Patuhi JUMLAH SCENE dan BUDGET KATA pada pesan pengguna. Durasi suara = jumlah kata / 2,2 detik.

FORMAT OUTPUT: hanya satu objek JSON (tanpa teks lain, tanpa markdown) dengan field PERSIS seperti ini
(isi contoh hanyalah ilustrasi format, jangan disalin):
{
  "topic": "<topik>",
  "target_duration_sec": 15,
  "bgm_mood": "corporate_minimal",
  "scenes": [
    {"scene_index": 1, "role": "hook", "narration": "...", "search_keywords": ["...", "..."],
     "headline_overlay": "MAKS EMPAT KATA", "transition": "fade"},
    {"scene_index": 2, "role": "explanation", "narration": "...", "search_keywords": ["..."],
     "headline_overlay": "...", "transition": "crossfade"},
    {"scene_index": 3, "role": "cta", "narration": "...", "search_keywords": ["..."],
     "headline_overlay": "...", "transition": "fade"}
  ]
}
Nilai yang diizinkan: role ∈ {hook, problem, explanation, solution, cta}; bgm_mood ∈ {corporate_minimal, energetic_tech, inspiring_ambient, dramatic_urgent}; transition ∈ {fade, crossfade, none}."""


class ScriptGenerationError(RuntimeError):
    """Naskah gagal dibuat setelah semua percobaan; `attempts` berisi ringkasan tiap kegagalan."""

    def __init__(self, message: str, attempts: Optional[List[dict]] = None):
        super().__init__(message)
        self.attempts = attempts or []


def plan_budget(target_sec: int) -> Dict[str, int]:
    """Jumlah scene dan anggaran kata dari durasi target."""
    scenes = 3 if target_sec <= 20 else 4 if target_sec <= 40 else 5
    spoken_sec = max(target_sec - SCENE_PAD_SEC * scenes, 5.0)
    total = round(spoken_sec * WORDS_PER_SEC)
    return {
        "scenes": scenes,
        "total_words": total,
        "min_words": int(total * 0.8),
        "max_words": int(total * 1.15) + 1,
    }


def _extract_json(text: str) -> Optional[dict]:
    """Ambil objek JSON pertama dari teks (abaikan <think>, pagar markdown, teks pengantar)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _first(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return None


def _norm_num(s: str) -> str:
    return s.replace(",", ".")


def _numbers(text: str) -> List[tuple]:
    return [(_norm_num(m.group(1)), bool(m.group(2)), m.group(0).strip())
            for m in re.finditer(r"(\d+(?:[.,]\d+)?)(\s*%)?", text or "")]


class VideoScriptwriter:
    """Membuat naskah storyboard terstruktur dari topik dan riset."""

    def __init__(self, llm_client: Optional[LLMClient] = None,
                 emit: Optional[Callable[..., None]] = None):
        self.llm = llm_client or LLMClient()
        self._emit = emit or (lambda *a, **k: None)
        self.last_meta: Dict[str, Any] = {}

    # ------------------------------------------------------------------ prompt

    @staticmethod
    def build_user_prompt(topic: str, target_sec: int, budget: Dict[str, int],
                          research_context: Optional[str]) -> str:
        per_scene = max(budget["total_words"] // budget["scenes"], 6)
        prompt = (
            f"TOPIK: {topic}\n"
            f"TARGET DURASI: {target_sec} detik\n"
            f"JUMLAH SCENE: {budget['scenes']} (urutan: hook, ..., cta)\n"
            f"BUDGET KATA NARASI: total {budget['min_words']}-{budget['max_words']} kata "
            f"(sekitar {per_scene} kata per scene)"
        )
        if research_context and research_context.strip():
            prompt += ("\n\nRISET (satu-satunya sumber klaim dan angka; jangan menambah di luar ini):\n"
                       f"{research_context.strip()}")
        else:
            prompt += ("\n\nRISET: tidak tersedia. Gunakan pengetahuan umum yang mapan saja, "
                       "tanpa angka, persentase, atau statistik.")
        return prompt

    # --------------------------------------------------------------- normalize

    @staticmethod
    def _normalize(data: dict, topic: str, target_sec: int) -> dict:
        for wrapper in ("script", "video_script", "storyboard", "data", "result"):
            inner = data.get(wrapper)
            if isinstance(inner, dict) and ("scenes" in inner or "storyboard" in inner):
                data = inner
                break

        raw_scenes = _first(data, "scenes", "storyboard", "scene_list")
        scenes: List[dict] = []
        if isinstance(raw_scenes, list):
            for i, s in enumerate(raw_scenes, 1):
                if not isinstance(s, dict):
                    continue
                role_raw = str(_first(s, "role", "type", "scene_role") or "").strip().lower()
                kw = _first(s, "search_keywords", "keywords", "broll_keywords", "b_roll_keywords", "broll")
                if isinstance(kw, str):
                    kw = [k for k in re.split(r"[,;|]", kw)]
                kw = [str(k).strip() for k in (kw or []) if str(k).strip()][:5]
                headline = str(_first(s, "headline_overlay", "headline", "overlay", "title") or "").strip().upper()
                trans = str(_first(s, "transition") or "crossfade").strip().lower().replace("-", "").replace(" ", "")
                if trans in ("dissolve", "crossdissolve"):
                    trans = "crossfade"
                if trans not in ALLOWED_TRANSITIONS:
                    trans = "crossfade"
                scenes.append({
                    "scene_index": i,
                    "role": ROLE_ALIASES.get(role_raw, role_raw),
                    "narration": str(_first(s, "narration", "voiceover", "voice_over", "text", "script") or "").strip(),
                    "search_keywords": kw,
                    "headline_overlay": headline[:50],
                    "transition": trans,
                })

        mood_raw = str(_first(data, "bgm_mood", "mood", "bgm") or "").lower()
        mood = next((m for m in ALLOWED_MOODS if m == mood_raw), None)
        if mood is None:
            for needle, m in (("corporate", "corporate_minimal"), ("minimal", "corporate_minimal"),
                              ("energ", "energetic_tech"), ("tech", "energetic_tech"),
                              ("inspir", "inspiring_ambient"), ("ambient", "inspiring_ambient"),
                              ("dramat", "dramatic_urgent"), ("urgent", "dramatic_urgent")):
                if needle in mood_raw:
                    mood = m
                    break
        return {
            "topic": topic,                       # topik selalu dari pengguna, bukan karangan model
            "target_duration_sec": max(15, min(60, int(target_sec))),
            "bgm_mood": mood or "corporate_minimal",
            "scenes": scenes,
        }

    # ---------------------------------------------------------------- validate

    @staticmethod
    def _validate_content(script: VideoScriptSchema, budget: Dict[str, int],
                          research_context: Optional[str], topic: str) -> List[str]:
        issues: List[str] = []
        scenes = script.scenes
        n = len(scenes)
        if not (max(2, budget["scenes"] - 1) <= n <= budget["scenes"] + 1):
            issues.append(f"Jumlah scene {n}; harus {budget['scenes']} (boleh ±1).")
        if scenes[0].role != "hook":
            issues.append("Scene pertama harus role 'hook'.")
        if scenes[-1].role != "cta":
            issues.append("Scene terakhir harus role 'cta'.")
        if BANNED_OPENERS.match(scenes[0].narration):
            issues.append("Hook memakai pembukaan klise (\"Tahukah Anda\"/\"Halo guys\"); ganti dengan pertanyaan tajam atau fakta.")
        if len(scenes[0].narration.split()) > 18:
            issues.append("Hook terlalu panjang (maks 15 kata).")

        words = sum(len(s.narration.split()) for s in scenes)
        if not (budget["min_words"] <= words <= budget["max_words"]):
            issues.append(
                f"Total narasi {words} kata; harus {budget['min_words']}-{budget['max_words']} kata "
                f"agar durasi sesuai target."
            )

        for s in scenes:
            kws = [k.lower() for k in s.search_keywords]
            if kws and all(k in GENERIC_KEYWORDS for k in kws):
                issues.append(f"Scene {s.scene_index}: keyword B-roll terlalu generik {s.search_keywords}; "
                              f"buat spesifik dan visual sesuai isi scene.")

        allowed = {_norm_num(m.group(0)) for m in re.finditer(r"\d+(?:[.,]\d+)?", f"{research_context or ''} {topic}")}
        bad: List[str] = []
        for s in scenes:
            for num, is_pct, raw in _numbers(f"{s.narration} {s.headline_overlay}"):
                if num in allowed:
                    continue
                if not is_pct and float(num) <= 10:  # "3 langkah", "5 menit" dsb. tidak dianggap statistik
                    continue
                bad.append(raw)
        if bad:
            issues.append(f"Angka tidak ada di riset/topik (dilarang mengarang): {sorted(set(bad))}.")
        return issues

    def _parse_and_check(self, raw: str, topic: str, target_sec: int, budget: Dict[str, int],
                         research_context: Optional[str]) -> tuple[Optional[VideoScriptSchema], List[str]]:
        data = _extract_json(raw)
        if data is None:
            return None, ["Output bukan JSON valid. Kirim HANYA satu objek JSON."]
        normalized = self._normalize(data, topic, target_sec)
        if not normalized["scenes"]:
            return None, ["Field 'scenes' tidak ditemukan atau kosong. Gunakan field persis seperti contoh format."]
        try:
            script = VideoScriptSchema.model_validate(normalized)
        except ValidationError as e:
            issues = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:8]]
            return None, issues
        return script, self._validate_content(script, budget, research_context, topic)

    # ---------------------------------------------------------------- generate

    def generate_script(self, topic: str, research_context: Optional[str] = None,
                        target_duration_sec: int = 30) -> VideoScriptSchema:
        budget = plan_budget(target_duration_sec)
        base = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self.build_user_prompt(topic, target_duration_sec, budget, research_context)},
        ]
        messages = list(base)
        attempts: List[dict] = []

        for attempt in range(1, MAX_ATTEMPTS + 1):
            resp = self.llm.chat(
                messages=messages,
                step="video_scriptwriter",
                response_format={"type": "json_object"},
                temperature=0.4,
            )
            raw = resp.choices[0].message.content or ""
            script, issues = self._parse_and_check(raw, topic, target_duration_sec, budget, research_context)
            if script is not None and not issues:
                self.last_meta = {
                    "attempts": attempt,
                    "words": sum(len(s.narration.split()) for s in script.scenes),
                    "research_used": bool(research_context and research_context.strip()),
                    "roles": [s.role for s in script.scenes],
                }
                return script

            attempts.append({"attempt": attempt, "issues": issues[:6]})
            self._emit("video_script_attempt_failed",
                       {"attempt": attempt, "max_attempts": MAX_ATTEMPTS, "issues": issues[:6],
                        "raw_preview": raw[:300]},
                       kind="warning", status="failed")
            feedback = ("Naskah sebelumnya DITOLAK karena:\n" + "\n".join(f"- {i}" for i in issues[:8]) +
                        "\n\nPerbaiki SEMUA poin dan kirim ulang JSON lengkap (hanya JSON, field persis seperti format).")
            messages = base + [
                {"role": "assistant", "content": raw[:4000]},
                {"role": "user", "content": feedback},
            ]

        last = attempts[-1]["issues"][:3] if attempts else []
        raise ScriptGenerationError(
            f"Scriptwriter gagal membuat naskah valid setelah {MAX_ATTEMPTS} percobaan. "
            f"Masalah terakhir: {'; '.join(last)}",
            attempts,
        )