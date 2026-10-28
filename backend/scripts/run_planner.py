"""Jalankan Agent 2.
Pakai riset tersimpan (hemat kuota Groq/Tavily):
    python -m scripts.run_planner "tips produktivitas kerja tim"
Riset baru dulu (Agent 1 -> Agent 2):
    python -m scripts.run_planner "tips produktivitas kerja tim" --fresh
"""
import json
import sys
from src.carousel import pipeline

args = [a for a in sys.argv[1:] if not a.startswith("--")]
topic = args[0] if args else "tips produktivitas kerja tim"
out = pipeline.run(topic, fresh="--fresh" in sys.argv)

print("\n===== RENCANA POST (AGENT 2) =====")
print(json.dumps(out["plan"], ensure_ascii=False, indent=2))
print("\nStatus validasi:", "LOLOS" if out["ok"] else "ADA MASALAH")
for i in out["issues"]:
    print("-", i)
print("\nDisimpan di output/plan_latest.json")