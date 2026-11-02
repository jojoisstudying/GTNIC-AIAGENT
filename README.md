# Optional local cutout dependency

`rembg` is optional and isolated in `backend/requirements-image-processing.txt` because its security-patched release requires Pillow 12.1+, while MoviePy 2.2.1 requires Pillow <12. Install it only in a separate image-processing environment. The main backend and CI use `backend/requirements.txt`.
# AI Social Media Automation Agent (Enterprise Edition) - GTNIC 2026

Platform otomasi konten media sosial berbasis **Autonomous Multi-Agent Architecture** untuk industri dan enterprise di Indonesia dengan jaminan konten profesional ("No-AI-Slop").

## Struktur Repositori

Proyek ini menggunakan struktur monorepo terpisah antara Backend AI Agent dan Frontend Web:

- **`backend/`**: Pipeline AI Agent (Research, Planning, Composition, Guardrail Quality Control, Direct Publishing, Event Cost Tracking).
- **`frontend/`**: Antarmuka web pengguna / Live Dashboard interaktif.

##  Setup Cepat

### Backend
Lihat panduan lengkap di [backend/SPEC.md](backend/SPEC.md).
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Frontend
Lihat panduan di [frontend/README.md](frontend/README.md).
```bash
cd frontend
# Install dependency & jalankan dev server
```
