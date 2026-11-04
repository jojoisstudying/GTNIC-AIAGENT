"""Registry deklaratif 10 agent SOCIALFLOW + adapter integrasi (spec 13.3 & 13.7).

Ini peta tanggung jawab (input/output/tools/modul nyata) yang bisa dibaca API/UI. Logika tetap berada di modulnya
masing-masing; registry ini tidak menggandakan kode.
"""
from __future__ import annotations

AGENTS = [
    {"name": "Research Agent", "module": "src.carousel.agents.research_agent", "inputs": ["topic", "industry", "brand_facts"],
     "outputs": ["research findings + sumber"], "tools": ["tavily", "instagram.get_my_recent_performance"]},
    {"name": "Strategy Agent", "module": "src.core.strategy", "inputs": ["enterprise profile", "insight analytics", "campaign", "riset"],
     "outputs": ["kalender 7 hari (ContentStrategyItem)"], "tools": ["llm"]},
    {"name": "Planner Agent", "module": "src.carousel.agents.planner", "inputs": ["calendar item", "riset", "brand"],
     "outputs": ["rencana slide / content brief"], "tools": ["llm"]},
    {"name": "Copywriter Agent", "module": "src.carousel.agents.planner + src.reels.agents.scriptwriter",
     "inputs": ["brief"], "outputs": ["caption, teks slide, naskah Reels"], "tools": ["llm"]},
    {"name": "Designer Agent", "module": "src.carousel.agents.designer", "inputs": ["rencana slide", "aset disetujui"],
     "outputs": ["slide JPEG 1080x1350"], "tools": ["playwright", "cloudflare image"]},
    {"name": "Video Agent", "module": "src.reels.pipeline", "inputs": ["naskah", "b-roll"],
     "outputs": ["Reels MP4 9:16"], "tools": ["edge-tts", "pexels", "moviepy"]},
    {"name": "QC Agent", "module": "src.carousel.tools.semantic_qc + src.carousel.tools.qc + src.reels.tools.qc_video",
     "inputs": ["design/video"], "outputs": ["QC result: errors/warnings"], "tools": ["dom qc", "semantic qc"]},
    {"name": "Publisher Agent", "module": "src.agents.publisher", "inputs": ["run disetujui"],
     "outputs": ["Publication (media_id, permalink)"], "tools": ["cloudinary", "instagram graph api"]},
    {"name": "Analyst Agent", "module": "src.core.analytics_ingest", "inputs": ["Publication"],
     "outputs": ["PostAnalytics + AnalyticsInsight"], "tools": ["instagram insights"]},
    {"name": "Feedback Agent", "module": "src.core.strategy (feedback_insight_id)", "inputs": ["AnalyticsInsight"],
     "outputs": ["penyesuaian kalender berikutnya"], "tools": ["llm"]},
]

# provider -> (kategori, env wajib). Dipakai untuk status integrasi; mengganti provider = ganti adapter di sini.
ADAPTERS = {
    "groq": ("llm", ["GROQ_API_KEY"]),
    "tavily": ("web_research", ["TAVILY_API_KEY"]),
    "instagram": ("social_publishing", ["IG_TOKEN", "IG_USER_ID"]),
    "cloudinary": ("media_storage", ["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"]),
    "cloudflare_ai": ("image_generation", ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"]),
    "pexels": ("stock_video", ["PEXELS_API_KEY"]),
    "edge_tts": ("text_to_speech", []),
    "telegram": ("notification", ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]),
}
