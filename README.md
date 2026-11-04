# SOCIALFLOW AI (GTNIC 2026) — Enterprise Social Media Operations Agent

Autonomous multi-agent: Enterprise Profile → Research → Strategy (kalender 7 hari) → Produksi (Carousel / Single Image / Reels)
→ QC → Approval → Publish Instagram → Analytics → Feedback Loop.

- `backend/` FastAPI + pipeline agent. Setup: `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && playwright install chromium`
  lalu salin `.env.example` ke `.env` dan isi kunci (GROQ, TAVILY, IG_*, CLOUDINARY_*, GTNIC_API_KEY).
- `frontend/` React dashboard (`npm ci && npm run dev`).
- Jalankan: `uvicorn src.api:app --reload` (set `SCHEDULER_ENABLED=true` untuk autopilot: riset harian, strategi mingguan,
  produksi otomatis item yang sudah disetujui, publish terjadwal, tarik analytics).
- Endpoint baru: `GET /api/v1/approvals`, `/api/v1/integrations`, `/api/v1/agents`. Header opsional `X-User-Name` mencatat siapa yang menyetujui.
- `rembg` opsional: lihat `backend/requirements-image-processing.txt`.
