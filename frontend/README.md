# Frontend AI Social Media Orchestrator (GTNIC 2026)

Antarmuka web interaktif untuk mendemonstrasikan **Auto-Content Agent: Autonomous Multi-Agent Content Engineering Orchestrator**.

Dibuat menggunakan stack standar industri yang paling mudah dikembangkan dan dipahami:
- **Framework:** React 19 + Vite (Super cepat, reload instan)
- **Styling:** Tailwind CSS (Modern, dark enterprise theme)
- **Icons:** Lucide React
- **Integration:** Terhubung langsung ke backend FastAPI via proxy port `8000`.

---

## 🚀 Fitur yang Tersedia di Frontend

1. **Autonomous Pipeline Generator:**
   - Input topik atau ide konten.
   - Pilihan format: **Carousel Instagram (1080x1350)** atau **Short Video Reels (9:16)**.
   - Pilihan opsi riset web langsung (*Live Tavily Search*).
2. **Real-time Agent Reasoning & Tool Calls Terminal:**
   - Menampilkan tahapan berpikir agen secara transparan (*Research*, *Planner*, *Designer*, *DOM QC*, *Pricing*).
   - Menampilkan log tool calls (Tavily, LLM Llama-3, Playwright, Cloudinary, dll.) beserta latensi dan biaya token per aksi.
3. **Interactive Slide Carousel Preview:**
   - Navigasi slide (Next/Previous).
   - Tampilan rasio 4:5 resolusi tinggi.
   - Review draf caption Instagram dan tagar yang dirancang agen.
4. **Direct Instagram Publishing:**
   - Tombol satu klik *"Publish to Instagram"* (idempotent API).
5. **Asset Library Explorer:**
   - Menampilkan katalog foto talent/model berlisensi resmi dengan status persetujuan (*consent check*).
6. **Deterministic Layout Engines Registry:**
   - Menampilkan katalog 30 layout engine editorial teruji tanpa risiko halusinasi atau teks tumpang tindih.

---

## 🛠️ Cara Menjalankan Frontend & Backend

### 1. Jalankan Backend (FastAPI)
Buka terminal 1:
```bash
cd backend
source /home/ranggajm/.venvs/ai/bin/activate
PYTHONPATH=. uvicorn src.api:app --reload --port 8000
```
Backend akan aktif di `http://localhost:8000`.

### 2. Jalankan Frontend (Vite)
Buka terminal 2:
```bash
cd frontend
npm run dev
```
Buka browser di: **`http://localhost:3000`**.

---

## 📂 Struktur Kode untuk Tim Frontend
- `src/App.jsx` : Komponen utama dashboard (Generator, Reasoning Log, Previewer, Asset Library, Layout Registry).
- `src/api.js` : Helper fetch API yang rapi dan modular untuk seluruh interaksi backend.
- `src/index.css` : Konfigurasi styling Tailwind CSS dan kustomisasi scrollbar.
- `vite.config.js` : Konfigurasi dev server & reverse proxy ke backend port 8000.
