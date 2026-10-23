# SPEC.md — Refactor pipeline poster IG

Dokumen ini adalah satu-satunya sumber arah untuk Copilot. Kerjakan SATU tugas per perintah, sesuai urutan di bagian "Tugas".

## Aturan untuk Copilot
- Jangan pakai LangChain/LangGraph. Hanya: pydantic v2, SQLAlchemy 2 + Alembic, tenacity, requests/httpx, python-dotenv.
- Jangan ubah perilaku agent yang sudah ada (prompt, guardrail, compositor) kecuali tugasnya menyebutkan.
- Jangan baca `.venv/`, `data/`, `output*/`.
- Semua kode baru punya type hint dan satu test pytest minimal.
- Tidak ada `except Exception: pass`. Error harus dicatat sebagai event, lalu di-raise atau dikembalikan secara eksplisit.
- Secret tidak boleh muncul di log, event, atau pesan error (redaksi token/key).
- Python 3.11/3.12. Pin semua dependency di `requirements.txt` (sertakan `cloudinary`).

## Struktur target
```
src/
  core/
    context.py      # RunContext
    db.py           # engine, session, models
    events.py       # EventEmitter
    pricing.py      # hitung biaya dari config/pricing.json
    keys.py         # KeyPool
    http.py         # HttpClient (retry/backoff + event)
    llm.py          # LLMClient (Groq, retry, usage, fallback model)
  agents/ ...       # tetap, tapi menerima ctx
  tools/ ...        # tetap, tapi memakai ctx.http / ctx.llm
config/pricing.json
migrations/         # Alembic
tests/
```

## Skema DB (SQLite, SQLAlchemy)
Semua tabel punya `created_at` (UTC). `id` run = uuid4 hex.

| Tabel | Kolom utama |
|---|---|
| `runs` | id, topic, brand_id, status (running/ok/failed/awaiting_approval), started_at, finished_at, tokens_in, tokens_out, cost_usd, error |
| `research_snapshots` | id, run_id, data_json, warnings_json, ok |
| `plans` | id, run_id, version (naik per revisi), ok, plan_json, issues_json |
| `designs` | id, run_id, plan_id, version, ok, result_json, preview_path |
| `assets` | (kolom lama) + run_id, sha256, kind (pose/cutout/slide/preview) |
| `events` | id, run_id, ts, step, kind, name, target, tokens_in, tokens_out, units, cost_usd, duration_ms, status, detail_json |
| `publications` | id, run_id, status (intent/published/failed), intent_at, media_id, permalink, caption, image_urls_json, error |
| `credentials_status` | provider, expires_at, last_refreshed_at, last_error, alerted_at |

Aturan: plan/research/design TIDAK pernah ditimpa. File `*_latest.json` diganti query "versi terbaru per run" (boleh tetap diekspor sebagai salinan).

## Event (tabel `events`)
`kind` salah satu dari:
- `llm` — name=model, tokens_in/out dari `usage`, cost dari pricing
- `tool` — name=nama tool, detail=argumen (tanpa secret)
- `http` — target=URL tanpa query secret, detail=status code, units=kredit (mis. Tavily)
- `retry` — alasan, percobaan ke-N, delay
- `key` — rotasi key (hanya id/hash 4 karakter, bukan key)
- `guardrail` — aturan yang gagal dan hasilnya
- `decision` — keputusan agent (mis. pilihan layout, alasan)
- `error`, `info`

Terminal menampilkan satu baris per event: `[12:03:41] research | llm gpt-oss-120b | in=2.1k out=380 | $0.0021 | 1.4s`.
Akhir run mencetak ringkasan: total token per agent, kredit Tavily, estimasi biaya, jumlah retry.

## Antarmuka inti

**RunContext** (dibuat satu kali per generate, dioper ke semua agent/tool):
`run_id, brand, session, emit(kind, name, **fields), llm, http, budget`

**EventEmitter.emit(...)** menulis ke DB dan terminal. Tidak boleh melempar error ke pemanggil.

**LLMClient.chat(messages, *, step, model=None, tools=None, response_format=None)**
- membungkus Groq, retry (tenacity: backoff eksponensial + jitter, maks 4 percobaan) untuk 429/5xx/timeout
- 429 → panggil `KeyPool.cooldown(key)` lalu coba key berikutnya; kalau semua key cooldown → pakai `FALLBACK_MODEL` bila ada, kalau tidak raise `ProviderExhausted`
- mencatat event `llm` dengan usage dan biaya
- menerapkan `ctx.budget` (maks token/biaya per run) → raise `BudgetExceeded`

**HttpClient.request(method, url, *, step, provider, ...)**
- timeout wajib, retry untuk 429/5xx/timeout, hormati header `Retry-After`
- redaksi `access_token`, `api_key`, `Authorization` dari semua log/event/error
- catat event `http`

**KeyPool(provider)**: membaca beberapa key dari env (`GROQ_API_KEYS=a,b,c`, `GROQ_API_KEY` tunggal tetap didukung). Round-robin, cooldown saat 429, key tidak pernah dicetak. Hanya untuk key milik sendiri/tim yang sah.

**Structured output**: planner dan research memakai Pydantic model + `response_format` JSON schema (fallback: parse JSON lalu validasi Pydantic). Hapus regex `\{.*\}`.

## Tugas (urut, satu per perintah)

### Fase 1 — Fondasi
1. Rapikan `requirements.txt` (pin, tambah `cloudinary`, SQLAlchemy, Alembic, tenacity, pydantic, pytest). Tambah `.env.example` lengkap. *Selesai bila:* `pip install -r` di venv baru berhasil.
2. `core/db.py` + migrasi Alembic untuk semua tabel di atas. Migrasikan tabel `assets` lama tanpa kehilangan data. *Selesai bila:* `alembic upgrade head` di DB lama berhasil dan `list_assets.py` tetap jalan.
3. `core/events.py` + `core/pricing.py` + `config/pricing.json`. *Selesai bila:* test memastikan satu event tertulis dan biaya terhitung.
4. `core/llm.py` (tanpa rotasi dulu): retry, usage, event. Ganti `_get_client()` di research dan planner. *Selesai bila:* `test_mock.py` lama masih lolos dan event `llm` muncul.
5. `core/http.py`: bungkus Tavily, Instagram, Cloudinary, Cloudflare. Redaksi secret. *Selesai bila:* test membuktikan token tidak muncul di log saat error.
6. `core/context.py`: `RunContext` dioper dari `pipeline.py`. Perluas `pipeline.run()` hingga mencakup Designer (dan Publisher sebagai langkah terpisah yang butuh persetujuan). *Selesai bila:* satu run penuh menghasilkan baris di `runs`, `research_snapshots`, `plans`, `designs`, dan `events`.
7. Simpan semua output ke DB (versi baru per revisi), file hanya salinan ekspor. Asset baru menyimpan `run_id` dan `sha256`.

### Fase 4 — Keandalan
8. `core/keys.py` + integrasi ke `LLMClient` dan Tavily. Fallback model di config.
9. Idempotensi publish: tulis `publications(status=intent)` SEBELUM memanggil IG; update ke `published` setelah sukses. Bila ada `intent` yang menggantung, tolak posting baru sebelum diperiksa manual. Hapus `except` yang menelan error di `wait_until_ready`.
10. `credentials_status` untuk token IG: simpan `expires_at`; refresh otomatis sebelum kedaluwarsa; bila gagal atau error 190, kirim alert (Telegram bot atau email; pilih salah satu lewat env) dan tandai `alerted_at` agar tidak spam. Cek status token di awal setiap run dan hentikan run publish bila kedaluwarsa.
11. Cek kuota publish IG (`content_publishing_limit`) sebelum posting.

### Fase 2 — Layout (kerjakan setelah fase 1 dan 4)
Pustaka layout parametrik di `src/layouts/`, satu file per layout, tiap layout menerima (teks, foto?, brand, parameter) dan mengembalikan gambar + metadata. Daftar awal:
`angka_besar`, `split_foto_teks`, `foto_penuh_overlay`, `kutipan`, `daftar_bernomor`, `perbandingan`, `tipografi_minimal`, `langkah_diagram`, `cta_blok`.
Planner mengeluarkan per slide: `layout_id`, `params`, `emphasis`. Kode memvalidasi ritme: tidak ada layout sama berurutan, cover berbeda dari isi, minimal 3 layout berbeda per carousel. Tambahkan file font ke repo, hapus ketergantungan pada font sistem.

### Fase 3 — QC visual (setelah fase 2)
Lapis 1 (kode): kontras, overflow, margin aman, ruang kosong, halo tepi cutout, pHash antar-slide, deteksi wajah untuk crop. Lapis 2: satu panggilan VLM pada contact sheet dengan rubrik terstruktur, output berupa aksi (`ganti_layout`, `perkecil_teks`, `generate_ulang_pose`). Maksimal 2 putaran, dengan batas biaya. Kalibrasi dengan 10–15 contoh bagus/jelek buatan sendiri sebelum dipercaya.

## Definisi selesai
- Fase 1: satu run lengkap tercatat di DB, ringkasan token/biaya per agent tercetak, tidak ada file `*_latest` yang ditimpa.
- Fase 4: mematikan jaringan atau memberi key salah menghasilkan retry dan event yang jelas, bukan crash diam-diam; posting tidak pernah ganda; token IG kedaluwarsa memicu alert.
- Fase 2: tiga carousel dengan topik berbeda tidak punya layout berulang berurutan.
- Fase 3: QC menolak contoh jelek dan meloloskan contoh bagus dari koleksi kalibrasi.