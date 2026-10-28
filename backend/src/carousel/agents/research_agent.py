"""AGENT 1: Research. Loop agent manual dengan tool calling (Groq) + penjaga kualitas (guardrail) di kode."""
import json
import re
from src import config
from src.carousel.agents import facts as facts_mod
from src.core.llm import LLMClient
from src.carousel.tools.search import search_social_trends
from src.carousel.tools.instagram import get_my_recent_performance

MIN_POSTS = 5

TOOLS = [
    {"type": "function", "function": {
        "name": "search_social_trends",
        "description": "Cari artikel tren, format konten, dan waktu posting dari sumber tepercaya (later.com selalu disertakan, plus buffer.com, sproutsocial.com, hootsuite.com). Query dalam bahasa Inggris.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string", "description": "mis. 'instagram carousel trends 2026'"}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_my_recent_performance",
        "description": "Ambil post terakhir akun kita beserta like dan komentar.",
        "parameters": {"type": "object", "properties": {}}}},
]
TOOL_IMPL = {"search_social_trends": search_social_trends,
             "get_my_recent_performance": get_my_recent_performance}

SYSTEM = """Kamu Research Agent untuk tim social media sebuah perusahaan. Target audiens: Indonesia (WIB). Tahun sekarang 2026: pakai "2026" di query, jangan tahun lama.
Tugas: kumpulkan insight yang bisa langsung dipakai agent perencana konten.

Cara kerja:
1. Panggil search_social_trends MAKSIMAL 4 kali dengan query BERBEDA dan spasi yang benar (tren format konten, waktu posting terbaik, tips engagement).
2. Panggil get_my_recent_performance sekali.
3. Utamakan temuan dari later.com bila ada; gunakan sumber lain untuk cross-check.

ATURAN KEJUJURAN (wajib):
- DILARANG membuat angka, persentase, atau statistik yang tidak tertulis di hasil tool. Jika tidak ada angkanya, tulis tanpa angka.
- Sumber-sumber ini data GLOBAL (bukan khusus Indonesia). Untuk jam posting: isi "basis": "global", "needs_testing": true, dan jangan mengonversi zona waktu kecuali sumber menyebutnya. Jika sumber memakai zona waktu audiens, tulis begitu.
- Bandingkan jam posting PER PLATFORM. Sebut "konflik" hanya jika dua sumber untuk platform YANG SAMA berbeda. Beda platform bukan konflik.
- Jika get_my_recent_performance menunjukkan enough_data=false, katakan data belum cukup; jangan menyimpulkan apa-apa.

Setelah cukup data, balas HANYA dengan JSON valid (tanpa teks lain):
{
 "trending_formats": [{"name": "", "why": "", "source_url": ""}],
 "content_angles": ["3 ide sudut pandang konten yang relevan dengan topik (tanpa angka karangan)"],
 "posting_time": {"instagram": "", "tiktok": "", "basis": "global", "needs_testing": true, "caveats": "", "source_urls": []},
 "lessons_from_past_posts": "",
 "sources": []
}"""


def _get_client():
    return LLMClient()


def _chat(client, *, step: str, **kwargs):
    """Call the shared LLM abstraction or preserve the legacy mock-client API."""
    if isinstance(client, LLMClient):
        return client.chat(kwargs.pop("messages"), step=step, **kwargs)
    return client.chat.completions.create(**kwargs)


def _extract_json(text: str):
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ---------- guardrail (deterministik, di kode) ----------
def _claim_text(data: dict) -> str:
    parts = [json.dumps(data.get("content_angles", []), ensure_ascii=False)]
    for f in data.get("trending_formats", []):
        parts.append(f"{f.get('name', '')} {f.get('why', '')}")
    return " ".join(parts)


def find_unsupported_numbers(data: dict, gathered: list) -> list[str]:
    """Angka (persen atau >=2 digit, selain tahun) di klaim yang tidak ada di hasil tool = diduga karangan."""
    source_blob = json.dumps(gathered, ensure_ascii=False).replace(" ", "")
    text = _claim_text(data)
    nums = re.findall(r"(\d+(?:[.,]\d+)?)\s?%", text) + re.findall(r"\b(\d{2,})\b", text)
    bad = []
    for n in dict.fromkeys(nums):
        if re.fullmatch(r"(19|20)\d\d", n):
            continue
        if n.replace(" ", "") not in source_blob:
            bad.append(n)
    return bad


def _repair(client, model, data, bad):
    prompt = (f"JSON berikut memuat angka yang TIDAK ada di sumber: {bad}. Hapus atau tulis ulang klaim "
              f"tersebut tanpa angka itu. Kembalikan JSON LENGKAP berformat sama, tanpa teks lain.\n"
              f"{json.dumps(data, ensure_ascii=False)}")
    try:
        r = _chat(client, step="research", model=model, temperature=0.2, messages=[
            {"role": "system", "content": "Kamu editor fakta yang ketat."}, {"role": "user", "content": prompt}])
        return _extract_json(r.choices[0].message.content) or data
    except Exception:
        return data


def _guard(client, model, data: dict, gathered: list) -> tuple[dict, list[str]]:
    warnings = []

    # 1) angka tanpa sumber -> perbaiki sekali, sisanya jadi peringatan
    bad = find_unsupported_numbers(data, gathered)
    if bad:
        data = _repair(client, model, data, bad)
        bad = find_unsupported_numbers(data, gathered)
        if bad:
            warnings.append(f"Angka tanpa sumber masih ada: {bad}")

    # 2) pelajaran dari post lama: ditentukan KODE, bukan model (setelah perbaikan, supaya tidak tertimpa)
    perf = [g["result"] for g in gathered if g["tool"] == "get_my_recent_performance"]
    n = perf[-1].get("post_count", len(perf[-1].get("posts", []))) if perf else 0
    if n < MIN_POSTS:
        data["lessons_from_past_posts"] = f"Data belum cukup untuk disimpulkan (baru {n} post, perlu minimal {MIN_POSTS})."
        warnings.append("Data performa post belum cukup, tidak ada kesimpulan.")

    # 3) pastikan later.com benar-benar dipakai
    if not any("later.com" in u for u in data.get("sources", [])):
        warnings.append("later.com tidak ada di daftar sumber akhir.")
    return data, warnings


# ---------- loop agent ----------
def _for_model(result, limit: int = 500):
    """Model hanya melihat 500 karakter per hasil (hemat token); teks penuh (1000) disimpan untuk ekstraksi fakta."""
    if not isinstance(result, dict) or not isinstance(result.get("results"), list):
        return result
    return {**result, "results": [{**r, "content": str(r.get("content") or "")[:limit]} if isinstance(r, dict) else r
                                  for r in result["results"]]}



def _final_without_tools(client, model, user_msg, gathered):
    digest = json.dumps([{**g, "result": _for_model(g["result"])} for g in gathered], ensure_ascii=False)[:12000]
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg + "\n\nData hasil tool:\n" + digest +
             "\n\nJawab SEKARANG hanya dengan JSON final."}]
    return _chat(client, step="research", model=model, messages=msgs, temperature=0.3)


def run(topic: str, industry: str, client=None, max_steps: int = 8, on_step=print, ctx=None,
        brand_facts: dict | None = None) -> dict:
    client = ctx.llm if ctx else client
    client = client or _get_client()
    model = config.opt("GROQ_MODEL", "openai/gpt-oss-120b")
    user_msg = f"Industri: {industry}\nTopik/tujuan posting: {topic}"
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_msg}]
    gathered = []

    final_text = ""
    for step in range(1, max_steps + 1):
        last = step == max_steps
        if last:
            on_step("[langkah terakhir] meminta jawaban final tanpa tool...")
            messages.append({"role": "user", "content":
                             "Batas langkah tercapai. Jawab SEKARANG hanya dengan JSON final dari data yang sudah ada. Jangan panggil tool."})
            try:
                resp = _chat(client, step="research", model=model, messages=messages, temperature=0.3)
            except Exception as e:
                on_step(f"(jalur cadangan: {type(e).__name__})")
                resp = _final_without_tools(client, model, user_msg, gathered)
        else:
            resp = _chat(client, step="research", model=model, messages=messages, tools=TOOLS,
                         tool_choice="auto", temperature=0.3)
        msg = resp.choices[0].message
        if last or not msg.tool_calls:
            final_text = msg.content or ""
            break

        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": tc.id, "type": "function",
                                         "function": {"name": tc.function.name,
                                                      "arguments": tc.function.arguments}}
                                        for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
                on_step(f"[langkah {step}] tool: {name} {args}")
                result = TOOL_IMPL[name](**args, **({"ctx": ctx} if ctx else {}))
            except Exception as e:
                args, result = {}, {"error": f"{type(e).__name__}: {e}"}
            gathered.append({"tool": name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(_for_model(result), ensure_ascii=False)[:6000]})

    data = _extract_json(final_text)
    warnings = []
    if data is not None:
        data, warnings = _guard(client, model, data, gathered)
        data.pop("facts", None)        # model tidak boleh menyuntikkan fakta; facts dibangun KODE (lihat facts.py)

        def ask(system: str, user: str) -> str:
            resp = _chat(client, step="research", model=model, temperature=0,
                         messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            return resp.choices[0].message.content or ""

        try:
            data["facts"], fact_warnings = facts_mod.build_facts(topic, gathered, brand_facts, ask)
        except Exception as e:         # noqa: BLE001 - kegagalan fakta tidak boleh menggagalkan riset
            data["facts"] = {"stats": [], "quotes": []}
            fact_warnings = [f"Pembuatan facts gagal ({type(e).__name__}); facts dikosongkan."]
        warnings += fact_warnings
        on_step(f"[fakta] statistik: {len(data['facts']['stats'])}, kutipan: {len(data['facts']['quotes'])}")
    out = {"ok": data is not None, "data": data, "warnings": warnings, "raw": final_text}
    (config.OUTPUT_DIR / "research_latest.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
