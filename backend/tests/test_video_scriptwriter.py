"""Scriptwriter: skema di prompt, normalisasi, validasi isi, retry dengan feedback, tanpa fallback."""
import json
from types import SimpleNamespace

import pytest

from src.video.scriptwriter import (
    MAX_ATTEMPTS, ScriptGenerationError, VideoScriptwriter, plan_budget,
)

TOPIC = "Apa itu HTTPS"


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, *, step, **kw):
        self.calls.append({"messages": messages, "step": step, **kw})
        content = self.replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def scene(i, role, narration, kws=("padlock browser address bar",), headline="HTTPS AMAN", transition="crossfade"):
    return {"scene_index": i, "role": role, "narration": narration,
            "search_keywords": list(kws), "headline_overlay": headline, "transition": transition}


HOOK = "Apa bedanya HTTP dan HTTPS di address bar browser kamu?"
EXPL = "HTTPS mengenkripsi data antara browser dan server, jadi password dan kartu kredit sulit disadap."
CTA = "Simpan video ini dan bagikan ke temanmu yang masih asal klik."


def good(**over):
    data = {"topic": TOPIC, "target_duration_sec": 15, "bgm_mood": "corporate_minimal", "scenes": [
        scene(1, "hook", HOOK, transition="fade"),
        scene(2, "explanation", EXPL, kws=("encrypted data server cables",)),
        scene(3, "cta", CTA, kws=("smartphone save button",), headline="SIMPAN & BAGIKAN", transition="fade"),
    ]}
    data.update(over)
    return json.dumps(data)


def make(replies, emitted=None):
    llm = FakeLLM(replies)
    emit = (lambda name, detail=None, **kw: emitted.append((name, detail, kw))) if emitted is not None else None
    return VideoScriptwriter(llm_client=llm, emit=emit), llm


def test_plan_budget_scales_with_duration():
    b15, b30, b60 = plan_budget(15), plan_budget(30), plan_budget(60)
    assert (b15["scenes"], b30["scenes"], b60["scenes"]) == (3, 4, 5)
    assert 28 <= b15["total_words"] <= 34       # ~2,2 kata/detik dikurangi jeda antar scene
    assert b15["min_words"] < b15["total_words"] < b15["max_words"]


def test_valid_first_try_uses_schema_in_prompt_and_forces_topic():
    sw, llm = make([good(topic="topik karangan model")])
    script = sw.generate_script(TOPIC, None, 15)

    assert script.topic == TOPIC
    assert [s.role for s in script.scenes] == ["hook", "explanation", "cta"]
    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["step"] == "video_scriptwriter"
    assert call["response_format"] == {"type": "json_object"}
    system, user = call["messages"][0]["content"], call["messages"][1]["content"]
    for field in ("scene_index", "search_keywords", "headline_overlay", "bgm_mood", "transition"):
        assert field in system                    # akar masalah lama: skema tidak pernah diberitahukan
    assert "TOPIK: Apa itu HTTPS" in user and "JUMLAH SCENE: 3" in user
    assert "RISET: tidak tersedia" in user
    assert sw.last_meta["attempts"] == 1 and sw.last_meta["research_used"] is False


def test_research_context_is_embedded_in_prompt():
    sw, llm = make([good()])
    sw.generate_script(TOPIC, "[1] Cloudflare — https://x.test\nHTTPS memakai TLS.", 15)
    user = llm.calls[0]["messages"][1]["content"]
    assert "HTTPS memakai TLS." in user and "RISET: tidak tersedia" not in user
    assert sw.last_meta["research_used"] is True


def test_drifted_field_names_and_enums_are_normalized():
    drifted = json.dumps({"video_script": {"mood": "Corporate Tech", "storyboard": [
        {"type": "Intro", "voiceover": HOOK, "keywords": "padlock browser, address bar", "headline": "https aman"},
        {"type": "Body", "voiceover": EXPL, "keywords": ["server cables"], "headline": "ENKRIPSI", "transition": "Cross-Fade"},
        {"type": "Outro", "voiceover": CTA, "keywords": ["save button"], "headline": "SIMPAN"},
    ]}})
    sw, llm = make([drifted])
    script = sw.generate_script(TOPIC, None, 15)

    assert len(llm.calls) == 1
    assert [s.role for s in script.scenes] == ["hook", "explanation", "cta"]
    assert script.scenes[0].search_keywords == ["padlock browser", "address bar"]
    assert script.scenes[0].headline_overlay == "HTTPS AMAN"
    assert script.scenes[1].transition == "crossfade"


def test_markdown_fence_and_think_block_are_tolerated():
    wrapped = "<think>mikir dulu...</think>\n```json\n" + good() + "\n```"
    sw, llm = make([wrapped])
    assert sw.generate_script(TOPIC, None, 15).scenes[0].role == "hook"
    assert len(llm.calls) == 1


def test_retry_feeds_back_issues_then_succeeds():
    emitted = []
    sw, llm = make(["maaf, ini naskahnya: bla bla", good()], emitted)
    script = sw.generate_script(TOPIC, None, 15)

    assert script.scenes[-1].role == "cta"
    assert len(llm.calls) == 2
    retry_msgs = llm.calls[1]["messages"]
    assert retry_msgs[-2]["role"] == "assistant" and "maaf" in retry_msgs[-2]["content"]
    assert "DITOLAK" in retry_msgs[-1]["content"]
    assert sw.last_meta["attempts"] == 2
    assert [e[0] for e in emitted] == ["video_script_attempt_failed"]
    assert emitted[0][2] == {"kind": "warning", "status": "failed"}


def test_raises_after_max_attempts_instead_of_generic_fallback():
    emitted = []
    sw, llm = make(["bukan json"] * MAX_ATTEMPTS, emitted)
    with pytest.raises(ScriptGenerationError) as exc:
        sw.generate_script(TOPIC, None, 15)
    assert len(llm.calls) == MAX_ATTEMPTS
    assert len(exc.value.attempts) == MAX_ATTEMPTS
    assert "gagal" in str(exc.value).lower()
    assert len(emitted) == MAX_ATTEMPTS


def test_invented_statistic_is_rejected_unless_in_research():
    invented = good().replace("sulit disadap", "turun 87% serangan")
    sw, llm = make([invented, good()])
    sw.generate_script(TOPIC, None, 15)
    assert len(llm.calls) == 2
    assert "87%" in llm.calls[1]["messages"][-1]["content"]

    sw2, llm2 = make([invented])
    sw2.generate_script(TOPIC, "Laporan: serangan turun 87% setelah HTTPS.", 15)
    assert len(llm2.calls) == 1  # angka ada di riset -> boleh


def test_generic_keywords_rejected():
    generic = json.loads(good())
    generic["scenes"][1]["search_keywords"] = ["business meeting", "office team"]
    sw, llm = make([json.dumps(generic), good()])
    sw.generate_script(TOPIC, None, 15)
    assert len(llm.calls) == 2 and "generik" in llm.calls[1]["messages"][-1]["content"]


def test_word_budget_violation_is_rejected():
    short = json.loads(good())
    for s in short["scenes"]:
        s["narration"] = "Cukup singkat saja ya"
    sw, llm = make([json.dumps(short), good()])
    sw.generate_script(TOPIC, None, 15)
    assert len(llm.calls) == 2 and "Total narasi" in llm.calls[1]["messages"][-1]["content"]


def test_cliche_hook_and_wrong_roles_are_rejected():
    bad = json.loads(good())
    bad["scenes"][0]["narration"] = "Tahukah Anda bedanya HTTP dan HTTPS di address bar browser?"
    bad["scenes"][2]["role"] = "solution"
    sw, llm = make([json.dumps(bad), good()])
    sw.generate_script(TOPIC, None, 15)
    feedback = llm.calls[1]["messages"][-1]["content"]
    assert "klise" in feedback and "'cta'" in feedback