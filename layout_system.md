# LAYOUT_SYSTEM.md — Renderer HTML + Library Layout Carousel IG

Dokumen ini adalah satu-satunya sumber arah untuk pekerjaan **renderer HTML/CSS, library layout (target ±30), upgrade planner/designer, dan alur pose baru**.
`SPEC.md` lama tetap berlaku untuk Fase 1 dan Fase 4 (sudah selesai). **Fase 2 dan Fase 3 di `SPEC.md` digantikan seluruhnya oleh dokumen ini.**

---

## 0. Aturan untuk Gemini CLI (WAJIB, baca dulu)

1. Kerjakan **SATU tugas per perintah**, sesuai urutan di bagian "Tugas". Setelah selesai, berhenti dan laporkan: file yang diubah, cara menjalankan, hasil test.
2. **Gerbang review manusia.** Pada tugas bertanda `🛑 GERBANG REVIEW`, berhenti total dan tunggu keputusan pemilik proyek. Dilarang lanjut ke batch/tugas berikutnya sebelum semua layout di batch itu berstatus `approved` atau `retired` (cek `meta.json`).
3. **Dilarang mengubah `status` layout menjadi `approved`.** Hanya pemilik proyek yang boleh (lewat `scripts/layout_status.py` atau edit manual). Layout buatanmu selalu `draft`.
4. **Dilarang membaca atau mencetak**: `.venv/`, `data/`, `output*/`, `.env`. Jangan pernah menaruh secret di log, event, atau pesan error.
5. Jangan ubah perilaku agent yang sudah ada (prompt, guardrail klaim, preflight) kecuali tugas menyebutkannya. Baca file yang relevan dulu sebelum mengubah: `src/agents/designer.py`, `src/agents/planner.py`, `src/agents/research_agent.py`, `src/tools/asset_library.py`, `src/tools/compositor.py`, `src/tools/cloudflare_pose_generator.py`, `src/core/context.py`, `config/brand.json`.
6. Semua kode baru: type hint, satu test pytest minimal per modul, tidak ada `except Exception: pass`. Error dicatat sebagai event lewat `ctx.emit`, lalu di-raise atau dikembalikan eksplisit.
7. Python 3.12. Pin semua dependency baru di `requirements.txt` (versi stabil terbaru saat dikerjakan). Tambahkan `.python-version`.
8. **LLM tidak pernah menulis HTML/CSS saat runtime.** Template ditulis sekarang (oleh kamu), diuji, lalu di-approve manusia. Planner hanya memilih dan mengisi slot.
9. Tidak boleh menyalin logo, stiker, atau elemen brand pihak lain dari folder `references/`. Referensi hanya untuk **teknik** (komposisi, lapisan, tipografi).
10. Jika repo memakai git, commit kecil per tugas dengan pesan yang jelas.

---

## 1. Tujuan dan prinsip

**Masalah saat ini:** compositor Pillow menghasilkan slide yang seragam (gradien + lingkaran sama, 60% area kosong, hierarki datar, foto bertabrakan dengan teks).

**Tujuan:** carousel yang terlihat profesional, berlapis, dan berbeda tiap post, dengan identitas brand tetap konsisten.

Prinsip:
- **Tiga lapisan terpisah:** *peran* (fungsi halaman, dipilih planner) → *layout* (susunan elemen untuk peran itu) → *style* (tampilan visual dari seed).
- **Palet brand dikunci** di `config/brand.json`. Variasi datang dari **komposisi, lapisan, dekorasi, dan tipografi**, bukan dari mengganti warna brand.
- **Variasi = ±30 layout matang × parameter × style pack bersertifikat seed**, bukan ratusan template manual.
- **Chrome (header/footer brand) adalah lapisan tetap** yang tidak disentuh planner.
- **Kualitas dijaga oleh kode:** validator, uji tekanan, QC dari DOM. Manusia menilai selera di gerbang review.

---

## 2. Struktur target

```
config/brand.json            # tambah: logo_path, chrome{}, fonts{}, tokens{}  (lihat bagian 4)
references/                  # screenshot referensi + notes.md (diisi pemilik proyek)
gallery/                     # keluaran contact sheet (di-.gitignore)
src/
  render/
    renderer.py              # Playwright: html -> jpg + laporan DOM
    assemble.py              # rakit layer stack: style + layout + chrome -> html
    base.css                 # token, reset, utilitas
    autofit.js               # auto-fit teks + laporan layout
    fonts/                   # woff2 lokal (lisensi OFL), tanpa CDN
  layouts/
    models.py                # Pydantic: LayoutMeta, SlotSpec, ParamSpec
    registry.py              # muat + validasi semua layout, filter status
    primitives/              # makro Jinja bersama (lihat bagian 5)
    style/packs.py           # generator style pack dari seed
    <layout_id>/
      layout.html            # Jinja2, autoescape ON
      layout.css
      schema.json            # slot + params
      meta.json              # role, status, density, needs_photo, pose_tags, tags, notes
      sample_data.json       # data contoh pendek/normal/maksimal
  agents/                    # planner.py, designer.py diupgrade
  tools/qc_dom.py            # QC lapis 1 dari laporan DOM
scripts/
  render_gallery.py          # contact sheet per batch
  layout_status.py           # approve / retire / draft (hanya dijalankan manusia)
  resume_run.py              # lanjutkan run yang menunggu aset
tests/
```

Dependency baru: `playwright`, `jinja2`, `imagehash` (opsional, untuk pHash). Setelah install: `playwright install chromium`.

---

## 3. Taksonomi peran halaman

`role` adalah enum tertutup. Tiap layout milik tepat satu peran.

| role | Fungsi |
|---|---|
| `cover` | Menghentikan scroll (hook) |
| `konteks` | Masalah / kenapa penting |
| `penjelasan` | Satu ide per halaman |
| `langkah` | Proses berurutan |
| `daftar` | Beberapa poin sejajar |
| `data` | Satu atau beberapa angka kunci |
| `perbandingan` | Salah vs benar, sebelum vs sesudah, mitos vs fakta |
| `bukti` | Kutipan, studi kasus, kredibilitas |
| `rangkuman` | Rekap / checklist |
| `cta` | Satu aksi yang bisa dilakukan di IG |

**Aturan CTA:** hanya aksi native IG (simpan, bagikan, komen kata kunci, ikuti, kirim DM). **Dilarang** tombol palsu seperti "Lihat Selengkapnya" atau "Klik di sini" karena tidak bisa diklik di gambar carousel.

---

## 4. Token brand dan style pack

### 4.1 `config/brand.json` (tambahkan, jangan hapus field lama)
Baca isi file lebih dulu, lalu perluas dengan bentuk berikut (sesuaikan nilai dengan yang sudah ada):
```json
{
  "tokens": {
    "bg": "#0B2A5B", "bg_alt": "#061A3A", "fg": "#FFFFFF",
    "accent": "#FFB400", "accent_fg": "#0B1B3A", "muted": "#9FB3D1"
  },
  "fonts": {
    "display": {"family": "Poppins", "file": "Poppins-ExtraBold.woff2", "weight": 800},
    "body": {"family": "Poppins", "file": "Poppins-Regular.woff2", "weight": 400},
    "hand": {"family": "Caveat", "file": "Caveat-Bold.woff2", "weight": 700}
  },
  "chrome": {
    "logo_path": null,
    "brand_text": "NAMA BRAND",
    "header": true,
    "footer": {"show": true, "lines": ["@handle", "kontak"], "qr_path": null},
    "page_counter": true
  }
}
```
- Jika `logo_path` kosong, pakai `brand_text` sebagai fallback.
- Font wajib berlisensi bebas (OFL) dan disimpan di `src/render/fonts/`. **Tidak boleh memuat font dari CDN atau font sistem.**

### 4.2 Style pack (dari seed)
Satu carousel = satu `style_pack` + satu `style_seed`, konsisten di semua slide carousel itu, berbeda antar post. Dihasilkan oleh `style/packs.py` secara deterministik dari seed, **di dalam token brand**.

Dimensi variasi:
- `pattern`: `grid_halus`, `titik`, `glow_radial`, `diagonal`, `polos_noise`, `garis_kontur`
- `deco`: bentuk (lingkaran, setengah lingkaran, blok, garis, bintang) dengan posisi, skala, dan opasitas dari seed. **Dilarang tetap pada satu komposisi dekorasi.**
- `accent_rule`: bagian mana yang boleh memakai warna aksen (kata kunci, nomor, garis, label). Aksen dipakai hemat.
- `texture`: `none` / `grain` / `paper`
- `continuity`: elemen yang menyeberang antar slide (garis, bentuk, props) agar saat di-swipe terasa satu kanvas. Dihitung dari urutan slide.

Output pack harus bisa diserialisasi (dict) dan disimpan di plan.

---

## 5. Renderer HTML

- Ukuran kanvas **1080×1350**, `deviceScaleFactor=1`, keluaran JPG kualitas 92.
- Playwright Chromium headless. **Blokir semua request jaringan eksternal** (render harus deterministik dan offline). Font dan gambar dimuat dari file lokal / data URI.
- `renderer.render(html, out_path) -> RenderResult` mengembalikan path dan **laporan DOM** (hasil `window.__layout_report`).
- `autofit.js`: untuk setiap elemen `[data-autofit]`, kecilkan font bertahap sampai muat (batas bawah `min_font_px` dari schema). Laporan berisi per elemen: `id`, `fits`, `final_font_px`, `overflow_px`, `bbox`, plus pasangan warna teks/latar untuk hitung kontras.
- Konten pengguna di-escape (Jinja autoescape). `emphasis` diterapkan lewat fungsi aman yang membungkus substring, bukan lewat `|safe` pada teks mentah.

### Layer stack (urutan z-index dari bawah)
1. `bg` — warna dasar + pattern dari style pack
2. `deco` — dekorasi style pack
3. `text_back` — teks di belakang subjek (hanya layout yang mendukung)
4. `photo` — cutout operator
5. `text_front` — judul, isi, label
6. `props` — elemen yang keluar frame / menyeberang kanvas
7. `chrome` — header + footer + penghitung halaman (selalu paling atas, tidak bisa dimatikan layout)

### Primitif bersama (`layouts/primitives/`)
Semua layout dirakit dari makro ini agar kualitas seragam. Minimal: `chrome`, `headline` (3 tingkat ukuran), `kicker` (label kecil), `highlight_label` (kotak berwarna di belakang teks), `panel` (kotak poin), `number_badge` (angka besar / bulat), `bullet_item`, `photo_wrap` (cutout + glow/shadow), `echo_text` (teks duplikat blur), `hand_note` (tulisan tangan aksen), `rope_prop` / `edge_prop` (elemen menyeberang tepi), `divider`.
Memperbaiki satu primitif memperbaiki semua layout yang memakainya.

### Aturan tipografi dan komposisi
- Hierarki **tiga tingkat jelas**: judul (sangat besar, kontras ekstrem), penopang (sedang), keterangan (kecil). Dilarang pola datar "judul – garis – paragraf" di semua halaman.
- Ukuran font minimum isi 30px, keterangan 24px (di kanvas 1080 lebar).
- Margin aman 64px dari semua tepi (kecuali elemen dekoratif / props yang memang menyeberang).
- Ruang kosong harus **disengaja**: tidak ada layout dengan separuh bawah kosong tanpa alasan komposisi.
- Kontras teks terhadap latar minimal 4.5:1 (teks besar ≥ 3:1).

### Yang harus dihindari (pola jelek dari versi lama)
Kotak kaca menutupi kepala subjek, dua lingkaran dekoratif yang selalu sama, tombol palsu, penomoran tidak konsisten (satu halaman bernomor, halaman langkah lain tidak), teks tipis di bagian atas dengan bawah kosong.

---

## 6. Spesifikasi satu layout

### `meta.json`
```json
{
  "id": "cover_teks_belakang_subjek",
  "role": "cover",
  "status": "draft",
  "density": "low",
  "needs_photo": "required",
  "pose_tags": ["senyum", "menunjuk"],
  "photo_crop": "half_body",
  "tags": ["effect:text_behind_subject", "echo_blur"],
  "reference_notes": "teknik dari references/..., bukan elemen brand",
  "batch": 2
}
```
- `role` ∈ enum bagian 3. `status` ∈ `draft | approved | retired`.
- `density` ∈ `low | medium | high`. `needs_photo` ∈ `none | optional | required`.
- `pose_tags` memakai kosakata pose di `asset_library` (saat ini: `senyum`, `mikir`, `menunjuk`, `pegang_laptop`, `pegang_tablet`, `tangan_disilang`; baca `asset_library.py` untuk daftar pasti).

### `schema.json`
```json
{
  "slots": {
    "title":    {"type": "text", "required": true,  "min_chars": 8,  "max_chars": 40, "min_font_px": 64, "emphasis": true},
    "subtitle": {"type": "text", "required": false, "max_chars": 80, "min_font_px": 32},
    "points":   {"type": "list", "required": false, "max_items": 4, "item_max_chars": 60}
  },
  "params": {
    "photo_side": {"enum": ["left", "center", "right"], "default": "center"},
    "title_scale": {"enum": ["m", "l", "xl"], "default": "l"},
    "align": {"enum": ["left", "center"], "default": "left"}
  }
}
```
Tipe slot: `text`, `list`, `number`, `image`, `icon`. Semua batas karakter ditegakkan oleh validator (bagian 9), bukan hanya oleh auto-fit.

### `sample_data.json`
Tiga set isi per layout: `min`, `typical`, `max` (panjang teks mendekati batas schema), dalam bahasa Indonesia yang natural, bukan lorem ipsum.

---

## 7. Uji tekanan dan gerbang otomatis

Untuk setiap layout: render **3 panjang teks (`min`/`typical`/`max`) × 3 seed = 9 render**. Jika `needs_photo=optional`, ulangi dengan dan tanpa foto. Layout **lolos** hanya jika semua render:
- tidak ada elemen overflow atau keluar kanvas (kecuali elemen bertanda `data-bleed`),
- font akhir ≥ batas minimum,
- kontras memenuhi,
- margin aman terpenuhi,
- chrome tidak tertutup.

Layout yang gagal **diperbaiki dulu (maks 3 iterasi otomatis)** sebelum ditampilkan ke pemilik proyek. Jika tetap gagal, laporkan di `report.md` sebagai `GAGAL OTOMATIS` beserta penyebabnya.

---

## 8. Alur batch dan gerbang review

Setiap batch memakai alur yang sama:

1. Tulis layout batch sebagai `draft`.
2. Jalankan `python scripts/render_gallery.py --batch N`. Keluaran di `gallery/batch_N/`:
   - `contact_sheet_<layout_id>.jpg` (grid 3×3: teks × seed),
   - `overview.jpg` (satu gambar ringkas semua layout batch),
   - `report.md` (hasil gerbang otomatis per layout).
3. Cetak: `🛑 MENUNGGU REVIEW BATCH N` lalu **berhenti**.
4. Pemilik proyek memberi keputusan per layout: `approve`, `perbaiki: <catatan>`, atau `buang`.
5. Perbaiki yang ditandai, render ulang hanya layout itu, berhenti lagi. Ulangi sampai tidak ada `draft` tersisa di batch.
6. Baru boleh mulai batch berikutnya.

Kamu **tidak boleh** menandai approve sendiri, dan tidak boleh mengerjakan batch berikutnya sambil menunggu.

### Target layout per batch (±30, boleh disesuaikan dengan catatan alasan)

| Batch | Isi | Layout |
|---|---|---|
| 1 — Inti | Satu carousel utuh bisa jalan | `cover_judul_raksasa`, `cover_foto_judul_bawah`, `penjelasan_teks_ikon`, `penjelasan_split_foto`, `daftar_bernomor`, `data_angka_besar`, `perbandingan_dua_kolom`, `cta_komen` |
| 2 — Cover efek | Cover berlapis | `cover_teks_belakang_subjek`, `cover_echo_blur`, `cover_pose_lelucon`, `cover_skala_objek`, `cover_dialog_meme`, `cover_pertanyaan_wajah_crop` |
| 3 — Isi | Halaman konten | `langkah_nomor_besar`, `langkah_timeline`, `panel_poin_highlight`, `gambar_berbingkai_caption`, `data_tiga_angka`, `bukti_kutipan` |
| 4 — Variasi isi | Kontras ritme | `perbandingan_sebelum_sesudah`, `perbandingan_mitos_fakta`, `konteks_pernyataan_besar`, `rangkuman_checklist`, `langkah_diagram_alur`, `penjelasan_tipografi_minimal` |
| 5 — CTA | Penutup | `cta_simpan_bagikan`, `cta_foto_ajakan`, `cta_pertanyaan_komen`, `cta_teks_besar` |

Total 30. Batch 2 paling sulit (efek lapisan, cutout bersih): kerjakan setelah primitif dan batch 1 stabil.

### Pedoman kreatif agar tidak generik
- Pakai tekniknya dari `references/`: teks di belakang kepala subjek, teks echo blur melayang, label kotak menyilang dada, objek berskala besar dengan figur kecil, props yang masuk dari tepi kanvas, grid halus + label sudut kecil di latar, glow di belakang subjek, tulisan tangan sebagai aksen.
- Satu layout = satu ide komposisi yang jelas. Jangan 30 variasi dari kotak + judul + paragraf.
- Kata kunci yang di-highlight (aksen) maksimal 1–2 per slide.

---

## 9. Skema planner dan validator

### 9.1 Output planner baru
Pertahankan field lama yang dipakai publisher (`concept`, `caption`, `hashtags`, `schedule`) dan guardrail klaim. Ganti struktur slide menjadi:
```json
{
  "concept": "...", "caption": "...", "hashtags": ["..."], "schedule": {"suggested_time": "..."},
  "style": {"seed": 482913, "pack_id": "grid_halus-7"},
  "slides": [
    {
      "index": 1, "role": "cover", "layout_id": "cover_teks_belakang_subjek",
      "slots": {"title": "...", "subtitle": "..."},
      "params": {"photo_side": "center", "title_scale": "xl"},
      "emphasis": ["kata kunci"],
      "pose": "menunjuk"
    }
  ]
}
```
Model Pydantic untuk plan, slide, dan style. Gunakan `response_format` JSON schema; fallback parse JSON lalu validasi Pydantic. **Hapus regex `\{.*\}`** di jalur ini.

### 9.2 Katalog untuk planner
`registry.catalog()` mengembalikan hanya layout `approved`, dalam bentuk ringkas (id, role, density, needs_photo, pose_tags, batas karakter per slot, tags). **Planner tidak pernah menerima HTML/CSS.** Jika ada pose yang belum punya aset `approved`, tandai di katalog (`pose_available: false`).

### 9.3 Konten terstruktur dari research
Perluas output research dengan `facts` bertipe: `stats[{value,label,source}]`, `steps[]`, `comparisons[{left,right}]`, `myths[{myth,fact}]`, `quotes[{text,source}]`. Planner hanya boleh memilih layout `data`/`perbandingan`/`langkah`/`bukti` jika bahan yang sesuai tersedia. Guardrail klaim dan angka yang sudah ada tetap berlaku.

### 9.4 Validator rencana (kode, bukan LLM)
Tolak rencana (dengan alasan jelas, lalu planner revisi maks 2×) jika:
1. `layout_id` tidak ada atau bukan `approved`.
2. `role` slide tidak sama dengan `role` layout.
3. Layout sama muncul berurutan.
4. Kurang dari 3 layout berbeda dalam satu carousel (jika ≥ 5 slide).
5. Slide 1 bukan `cover`, atau slide terakhir bukan `cta`.
6. Slot wajib kosong, melebihi `max_chars` / `max_items`, atau params di luar enum.
7. `emphasis` berisi teks yang tidak ada di slot.
8. Layout `needs_photo=required` tanpa `pose` yang valid.
9. Layout bertipe `data`/`bukti` tanpa bahan fakta pendukung dari research.
10. Terlalu banyak halaman `density=high` berturut-turut (maks 2).
11. Pelanggaran memori anti-ulang (bagian 9.5).

### 9.5 Memori anti-ulang
Tambah tabel `layout_usage` lewat migrasi Alembic baru: `id, run_id, slide_index, layout_id, role, style_pack_id, style_seed, created_at`. Diisi saat plan disimpan. Planner menerima ringkasan 8 post terakhir. Aturan keras: layout `cover` tidak boleh sama dengan cover dari 3 post terakhir; `style.pack_id` tidak boleh sama dengan post sebelumnya.

---

## 10. Designer baru

Pertahankan antarmuka: `designer.run(plan, brand, out_dir, ctx)` dan **bentuk hasil** yang dibaca `publisher.preflight` (`ok`, `warnings`, `preview`, `pending_review`, dan `slides[]` dengan `index`, `path`, `has_photo`, `photo_path`, `placeholder`, `issues`). Baca `designer.py` lebih dulu dan jaga kompatibilitasnya.

Alur:
1. Muat layout dari registry, bangun style pack dari `style.seed`.
2. Rakit HTML (`assemble.py`) → render (`renderer.py`) → ambil laporan DOM.
3. QC lapis 1 (`tools/qc_dom.py`): overflow, kontras, ukuran font, margin aman, chrome utuh, pHash antar-slide (tidak ada dua slide nyaris identik), tepi cutout (cek halo dari alpha foto).
4. Jika gagal, lakukan **aksi terbatas** (daftar tertutup): `perkecil_teks`, `ganti_layout_sepadan` (layout approved lain dengan peran sama dan slot kompatibel), `minta_pose_baru`. Maksimal 2 putaran per slide, semua tercatat sebagai event `decision`. **Tidak ada CSS bebas.**
5. Buat `preview.jpg` (contact sheet semua slide).

Flag `RENDERER=html|pillow` di `.env` / config. Default tetap `pillow` sampai tugas R8 selesai dan disetujui; compositor Pillow dipertahankan sebagai fallback.

---

## 11. Pose otomatis dengan persetujuan

Aturan:
1. Saat planner memilih layout dengan `pose` yang **belum punya aset `approved`**, ia boleh (a) memilih layout lain yang tidak butuh pose itu, atau (b) meminta pose baru.
2. Permintaan pose baru memanggil `cloudflare_pose_generator` (hormati flag `CLOUDFLARE_POSE_GENERATION`), menyimpan hasil sebagai asset `kind=pose` lalu cutout `kind=cutout` dengan `status=pending`, `run_id`, dan `sha256`. Deduplikasi berdasarkan `sha256` dan (person, tag).
3. Aset `pending` **tidak boleh dipakai di desain**. Run yang menunggu aset berstatus `awaiting_assets` (tambahkan nilai ini; sesuaikan migrasi bila `runs.status` dibatasi).
4. Pemilik proyek meng-approve lewat `scripts/approve_asset.py` (yang sudah ada). Lalu `scripts/resume_run.py <run_id>` melanjutkan langkah designer dari plan yang sama.
5. Batas biaya: maksimal N pose baru per run (default 3, dari config) agar tidak looping. Setiap permintaan dicatat sebagai event `decision` dengan alasan.
6. **Perbaiki `preflight`:** pemeriksaan `pending_assets()` harus dibatasi pada aset yang **dipakai run ini**, bukan seluruh DB, agar aset pending run lain tidak memblokir publish.
7. Validasi cutout (`asset_library.is_cutout`) tetap wajib sebelum foto dipakai di layout efek (teks di belakang subjek).

---

## 12. QC lapis 2 (VLM) — opsional, paling akhir

Satu panggilan VLM pada contact sheet dengan rubrik terstruktur. Output hanya **aksi dari daftar tertutup**: `ganti_layout`, `perkecil_teks`, `generate_ulang_pose`, `lolos`. Maksimal 2 putaran, dengan batas biaya lewat `ctx.budget`. Kalibrasi dengan 10–15 contoh bagus/jelek buatan pemilik proyek sebelum dipercaya. **Jangan dikerjakan sebelum R1–R8 selesai dan disetujui.**

---

## 13. Tugas (urut, satu per perintah)

### Fase R-A — Fondasi renderer
**R1.** Setup dependency (`playwright`, `jinja2`, `imagehash`), `.python-version`, font OFL ke `src/render/fonts/`, perluasan `config/brand.json` (bagian 4.1), `.gitignore` tambah `gallery/`. *Selesai bila:* `pip install -r requirements.txt` + `playwright install chromium` berhasil di venv baru.

**R2.** `render/renderer.py`, `base.css`, `autofit.js`, blokir jaringan eksternal, laporan DOM. *Selesai bila:* test merender halaman contoh ke JPG 1080×1350 dan laporan DOM berisi `fits`/`final_font_px`; request eksternal diblokir.

**R3.** `layouts/models.py`, `registry.py`, `style/packs.py`, `assemble.py` + layer stack + chrome. *Selesai bila:* seed yang sama menghasilkan style pack identik, seed berbeda menghasilkan dekorasi dan pola berbeda; test registry menolak layout dengan schema/meta tidak valid.

**R4.** Primitif bersama (`layouts/primitives/`), `scripts/render_gallery.py`, `scripts/layout_status.py`, uji tekanan otomatis (bagian 7), dan **satu layout contoh** (`cover_judul_raksasa`) sampai lolos gerbang otomatis. *Selesai bila:* `render_gallery.py --batch 1` menghasilkan contact sheet 3×3 + `report.md`.
> 🛑 **GERBANG REVIEW R-A:** berhenti, tunggu pemilik proyek menilai fondasi (tipografi, chrome, kualitas render) sebelum lanjut.

### Fase R-B — Library layout (bertahap)
**R5.** Batch 1 (8 layout inti) → 🛑 GERBANG REVIEW BATCH 1.
**R6.** Batch 2 (cover efek) → 🛑 GERBANG REVIEW BATCH 2.
**R7.** Batch 3, 4, 5 → masing-masing 🛑 GERBANG REVIEW. Batch berikutnya hanya setelah batch sebelumnya bebas `draft`.

> Tugas R8–R11 dikerjakan **setelah Batch 1 approved** (cukup untuk satu carousel utuh). Batch 2–5 boleh berjalan paralel dengan waktu review pemilik.

### Fase R-C — Integrasi
**R8.** Skema planner baru (bagian 9.1–9.2), konten terstruktur research (9.3), validator (9.4), tabel `layout_usage` + memori anti-ulang (9.5), Pydantic + `response_format`, hapus regex JSON di jalur ini. *Selesai bila:* test membuktikan tiap aturan validator menolak kasus yang sesuai, dan satu run `--fresh` menghasilkan plan valid yang hanya memakai layout `approved`.

**R9.** Designer baru (bagian 10) + `tools/qc_dom.py` + flag `RENDERER`. *Selesai bila:* satu run penuh menghasilkan 5–7 slide JPG, `preview.jpg`, baris di `designs`, event `decision` untuk setiap perbaikan otomatis, dan `publisher.preflight` tetap bisa membaca hasilnya (dry-run lolos).

**R10.** Alur pose otomatis + approval (bagian 11), status `awaiting_assets`, `resume_run.py`, perbaikan `preflight` per-run. *Selesai bila:* test simulasi: pose tidak tersedia → aset `pending` dibuat → run `awaiting_assets` → setelah approve dan `resume_run` desain selesai; aset run lain yang pending tidak memblokir.

**R11.** Ringkasan akhir run: tampilkan layout dan style pack terpilih per slide, jumlah perbaikan otomatis, pose baru diminta, token dan biaya. Ubah default `RENDERER=html` hanya jika pemilik proyek menyetujui.
> 🛑 **GERBANG REVIEW R-C:** tiga carousel dengan topik berbeda dihasilkan dan diperiksa pemilik proyek.

### Fase R-D — Opsional
**R12.** QC lapis 2 (bagian 12), setelah kalibrasi tersedia.

---

## 14. Definisi selesai

- **R-A:** satu layout lolos uji tekanan; contact sheet terbaca jelas; render offline dan deterministik untuk seed yang sama.
- **R-B:** ±30 layout berstatus `approved` (yang tidak lolos review berstatus `retired`); tiap layout lolos uji tekanan 9 render.
- **R-C:** tiga carousel berbeda topik tidak punya layout cover yang sama dengan 3 post sebelumnya, tidak ada layout berurutan sama, minimal 3 layout berbeda per carousel; style pack berbeda antar post; tidak ada aset `pending` yang masuk ke desain; run tercatat lengkap (`runs`, `plans`, `designs`, `events`, `layout_usage`).
- **Semua fase:** test pytest lulus, tidak ada secret di log, tidak ada `except` yang menelan error, tidak ada font/jaringan eksternal saat render.