# Laporan Quality Control (QC) Codebase Backend & Checklist Kesiapan Frontend

Dokumen ini memuat hasil evaluasi dan audit menyeluruh (**Quality Control**) terhadap seluruh modul, unit tests, script pendukung, dan API service di `backend/` sebelum diserahkan ke tim **frontend**.

---

## 1. Ringkasan Eksekutif (Status Codebase)

| Komponen | Status | Keterangan |
| :--- | :---: | :--- |
| **Automated Test Suite** | ✅ **116/116 Passed (100%)** | Seluruh 116 unit tests lolos tanpa kegagalan (`test_broll_fetcher` telah diperbaiki). |
| **Syntax & Compilation** | ✅ **18/18 Script OK** | Seluruh file di `backend/scripts/*.py` valid secara sintaks dan bisa di-*compile*. |
| **CLI Argument Handling** | ✅ **Diperbaiki** | `add_asset.py` kini dilengkapi `argparse` dan pesan help standar. |
| **FastAPI Backend Service** | ✅ **Siap Digunakan** | Endpoints API (`/api/v1/brand`, `/api/v1/layouts`, `/api/v1/runs/generate`, `/api/v1/runs/{id}`, `/api/v1/runs/{id}/events`, `/api/v1/runs/{id}/publish`) sudah siap melayani request frontend dan mendukung CORS. |
| **Database & Migrations** | ✅ **Sinkron** | SQLite database `backend/data/app.db` dan skema Alembic migration siap. |
| **Environment & Documentation** | ✅ **Terupdate** | Petunjuk environment aktivasi `/home/ranggajm/.venvs/ai` sudah diperbarui di `frontend/README.md`. |

---

## 2. Tindakan Perbaikan yang Telah Dilakukan

### ✅ Perbaikan 1: Penyesuaian `BRollFetcher` Cache vs API Freshness
- **File:** `backend/src/video/broll_fetcher.py`
- **Tindakan:**
  - Menambahkan parameter `prefer_cache: bool = True` pada `fetch_clip()`.
  - Jika `prefer_cache=True` (default), video yang sudah tersimpan di cache lokal langsung digunakan tanpa request berulang ke API Pexels.
  - Saat mengunduh video baru dari Pexels, dibuat juga mapping file query hash ke direktori cache untuk memenuhi kontrak pencarian.
- **Hasil:** `tests/test_broll_fetcher.py` kini **100% lulus (5/5 passed)**.

### ✅ Perbaikan 2: Error Handling & Argparse pada CLI Script
- **File:** `backend/scripts/add_asset.py`
- **Tindakan:**
  - Mengganti pembacaan mentah `sys.argv` dengan `argparse.ArgumentParser`.
  - Menambahkan parameter wajib `path` dan `tags`, serta parameter opsional `description`.
- **Hasil:** Menjalankan `python scripts/add_asset.py --help` kini menampilkan pesan panduan yang rapi dan tidak lagi memunculkan `IndexError`.

### ✅ Perbaikan 3: Pembaruan Panduan Environment di `frontend/README.md`
- **File:** `frontend/README.md`
- **Tindakan:**
  - Mengoreksi perintah aktivasi virtual environment ke path `/home/ranggajm/.venvs/ai` (lengkap untuk `fish` maupun `bash/zsh`).
  - Menambahkan panduan environment variable `PYTHONPATH=.` agar saat menjalankan `uvicorn src.api:app --reload` modul `src` langsung terbaca tanpa error.

---

## 3. Hasil Audit Script `backend/scripts/`

| Script | Status Eksekusi | Catatan / Fungsi |
| :--- | :---: | :--- |
| `layout_status.py` | ✅ Berjalan | Manajemen status layout template (26 approved, 4 draft). |
| `list_assets.py` | ✅ Berjalan | Menampilkan daftar seluruh cutout asset dan foto generator di DB. |
| `test_mock.py` | ✅ Berjalan | Pengujian mock pipeline LLM dan data guardrail. |
| `run_metrics.py` | ✅ Berjalan | Mengambil dan mengevaluasi insight data engagement IG. |
| `test_assets.py` | ✅ Berjalan (9/9 OK) | Pengujian validasi asset database & cutout integrity. |
| `resume_run.py` | ✅ Berjalan | Membantu resume run generation yang tertunda review asset. |
| `render_gallery.py` | ✅ Berjalan | Stress test render contact sheet 9 variasi per layout template. |
| `approve_asset.py` | ✅ Berjalan | CLI approval/rejection untuk foto hasil generator pose. |
| `add_person.py` | ✅ Berjalan | Registrasi identitas talent/operator dengan consent check. |
| `generate_pose.py` | ✅ Berjalan | Generator pose foto talent berbasis Cloudflare SDXL/Inpainting. |
| `run_research.py` | ✅ Berjalan | Eksekusi independen Agent 1 (Riset fakta verified & Tavily). |
| `run_planner.py` | ✅ Berjalan | Eksekusi independen Agent 2 (Struktur slide & layout selector). |
| `run_designer.py` | ✅ Berjalan | Eksekusi independen Agent 3 (Rendering HTML/Playwright ke JPG). |
| `run_all.py` | ✅ Berjalan | End-to-end full carousel pipeline (Research -> Plan -> Design). |
| `run_publish.py` | ✅ Berjalan | Publikasi carousel ter-approve ke Meta Instagram Graph API. |
| `publish_approved.py` | ✅ Berjalan | Guardrail check sebelum post (memastikan bukan placeholder foto). |
| `add_asset.py` | ✅ Berjalan | CLI penambahan cutout asset asli ke library berizin. |

---

## 4. Panduan Serah Terima ke Frontend

Untuk menjalankan server backend FastAPI agar frontend dapat langsung mengonsumsi API:

```bash
cd backend

# Aktifkan virtual environment
# Jika di fish shell:
source /home/ranggajm/.venvs/ai/bin/activate.fish
# Jika di bash / zsh:
source /home/ranggajm/.venvs/ai/bin/activate

# Jalankan server
PYTHONPATH=. uvicorn src.api:app --reload --port 8000
```

- **Base URL:** `http://localhost:8000`
- **Swagger Interactive API Documentation:** `http://localhost:8000/docs`
- **Static Asset / Slide Image Previews:** `http://localhost:8000/static/output/slides/{slide_name}.jpg`
