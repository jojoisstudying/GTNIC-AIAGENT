"""Jalankan Agent 1. Contoh:
python -m scripts.run_research "tips produktivitas kerja tim" "perusahaan manufaktur"
"""
import json
import sys
from pathlib import Path
from src.carousel.agents import research_agent

topic = sys.argv[1] if len(sys.argv) > 1 else "tips produktivitas kerja tim"
industry = sys.argv[2] if len(sys.argv) > 2 else "perusahaan umum"
brand_path = Path(__file__).resolve().parents[1] / "config" / "brand.json"
brand_facts = json.loads(brand_path.read_text(encoding="utf-8")).get("verified_facts") if brand_path.exists() else None
out = research_agent.run(topic, industry, brand_facts=brand_facts)
print("\n===== HASIL AGENT 1 =====")
print(json.dumps(out["data"] if out["ok"] else out["raw"], ensure_ascii=False, indent=2))
if out.get("warnings"):
    print("\n===== PERINGATAN GUARDRAIL =====")
    for w in out["warnings"]:
        print("-", w)
print("\nDisimpan di output/research_latest.json")
