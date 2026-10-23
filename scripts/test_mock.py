"""Tes guardrail & loop TANPA internet/API key."""
import json
from types import SimpleNamespace as NS
from src.agents import research_agent as ra

ra.TOOL_IMPL["search_social_trends"] = lambda query: {"results": [
    {"title": "t", "url": "https://later.com/blog/x", "content": "carousels get up to 20 slides"}]}
ra.TOOL_IMPL["get_my_recent_performance"] = lambda: {"posts": [{"id": "1"}], "post_count": 1, "enough_data": False}

BAD = {"trending_formats": [{"name": "Carousel", "why": "up to 20 slides", "source_url": "https://later.com/blog/x"}],
       "content_angles": ["Toolbox talk yang naikkan output 12 %"],
       "posting_time": {"instagram": "x", "tiktok": "y", "basis": "global", "needs_testing": True, "caveats": "", "source_urls": []},
       "lessons_from_past_posts": "engagement rendah", "sources": ["https://buffer.com/a"]}
FIXED = json.loads(json.dumps(BAD)); FIXED["content_angles"] = ["Toolbox talk harian singkat"]


def create(**kw):
    msgs = kw["messages"]
    if "tools" in kw:
        i = sum(1 for m in msgs if m["role"] == "tool")
        name, args = (("search_social_trends", '{"query":"q"}') if i == 0 else ("get_my_recent_performance", "{}"))
        if i >= 2:
            return NS(choices=[NS(message=NS(content=json.dumps(BAD), tool_calls=None))])
        tc = NS(id=f"c{i}", function=NS(name=name, arguments=args))
        return NS(choices=[NS(message=NS(content=None, tool_calls=[tc]))])
    if "editor fakta" in msgs[0]["content"]:
        return NS(choices=[NS(message=NS(content=json.dumps(FIXED), tool_calls=None))])
    raise AssertionError("panggilan tak terduga")


out = ra.run("tes", "tes", client=NS(chat=NS(completions=NS(create=create))), on_step=lambda m: None)
d = out["data"]
assert "12" not in json.dumps(d["content_angles"]), "angka karangan harus hilang"
assert d["lessons_from_past_posts"].startswith("Data belum cukup"), d["lessons_from_past_posts"]
assert any("later.com" in w for w in out["warnings"]), out["warnings"]
print("MOCK LOLOS. Peringatan:", out["warnings"])
