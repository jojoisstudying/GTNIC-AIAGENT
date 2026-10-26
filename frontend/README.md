# Frontend Workspace

Folder ini disiapkan untuk antarmuka pengguna (Web Interface / Dashboard AI Agent).

## 🔗 Integrasi Backend API

Backend AI Agent menggunakan **FastAPI**. Ketika backend berjalan, teman frontend dapat langsung mengakses:
- **Base URL:** `http://localhost:8000`
- **Swagger Interactive Docs:** `http://localhost:8000/docs` (bisa langsung dicoba di browser)

---

### 📋 Ringkasan Endpoint untuk Frontend

#### 1. Inisialisasi & Pengaturan
- **`GET /api/v1/brand`**
  - Mengambil data brand: nama, industri, palet warna hex (`primary`, `accent`, dll.), font, dan logo.
- **`GET /api/v1/layouts`**
  - Mengambil daftar template layout carousel yang tersedia (role, slot input teks, density, dll.).

#### 2. Generate Konten (AI Pipeline)
- **`POST /api/v1/runs/generate`**
  - Request Body:
    ```json
    {
      "topic": "Strategi Kelola Keuangan Usaha 2026",
      "fresh": true,
      "include_design": true
    }
    ```
  - Response:
    ```json
    {
      "run_id": "c1f7b8...",
      "status": "running",
      "message": "AI Agent sedang memproses riset, perencanaan slide, dan rendering."
    }
    ```

#### 3. Cek Status & Preview Hasil Carousel (Polling)
- **`GET /api/v1/runs/{run_id}`**
  - Mengembalikan status: `"running"`, `"ok"`, `"awaiting_approval"`, atau `"failed"`.
  - Jika selesai, mengembalikan:
    - `plan`: Data teks slide, judul, caption IG, hashtag, dan jadwal posting.
    - `design.slides`: Array slide dengan link gambar langsung (`image_url: "/static/output/slides/slide_1.jpg"`).
    - `cost_usd`: Total biaya token LLM.
    - `tokens_in` / `tokens_out`: Jumlah token yang terpakai.

#### 4. Thought Process / Log Agent (Pilar Otonomi Penilaian Lomba)
- **`GET /api/v1/runs/{run_id}/events`**
  - Mengembalikan riwayat aktivitas agen secara berurutan:
    - *"Agent 1: Researching keyword on Tavily..."*
    - *"Agent 2: Planning 7 slides with anti-repetition memory..."*
    - *"Designer: Rendering HTML slide 1 with Playwright..."*
    - *"QC DOM: Overflow check passed (1080x1350)..."*
  - **Saran UI:** Tampilkan di panel collapsible/sidebar *"Agent Activity Log"* agar juri terkesima dengan kecerdasan reasoning agen.

#### 5. Publikasikan ke Instagram
- **`POST /api/v1/runs/{run_id}/publish`**
  - Request Body: `{}` (menggunakan run_id dari path).
  - Mempublikasikan carousel langsung ke Instagram feed melalui Meta Graph API.

---

### 🚀 Menjalankan Server Backend untuk Development Frontend

Di folder `backend`:
```bash
# Aktifkan virtual environment (gunakan environment Python AI):
# Jika menggunakan fish shell:
source /home/ranggajm/.venvs/ai/bin/activate.fish
# Atau jika menggunakan bash / zsh:
source /home/ranggajm/.venvs/ai/bin/activate

# Jalankan server FastAPI (pastikan PYTHONPATH diset ke direktori backend):
PYTHONPATH=. uvicorn src.api:app --reload --port 8000
```
Server akan aktif di `http://localhost:8000` dan Swagger Docs di `http://localhost:8000/docs`.
