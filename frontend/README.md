# GTNIC — Frontend Asisten Pemasaran AI untuk UMKM

Antarmuka web untuk **AI Social Media Operations Agent (GTNIC 2026)**. Frontend ini hanya
mengonsumsi API FastAPI yang sudah ada di folder `backend/`; tidak ada perubahan kontrak API.

## Stack

- **React 19 + Vite** — tanpa state library tambahan.
- **Tailwind CSS** — design system berbasis token warna.
- **lucide-react** — ikon (ikon merek Instagram/Facebook dibuat lokal karena tidak tersedia di paket).
- **clsx + tailwind-merge** — komposisi className.
- Proxy Vite: `/api` dan `/static` diteruskan ke `http://localhost:8000`.

## Menjalankan

```bash
# 1. Backend (dari folder backend/)
uvicorn src.api:app --port 8000

# 2. Frontend (dari folder frontend/)
npm install
npm run dev      # http://localhost:3000
npm run build    # build produksi ke dist/
npm run lint
```

Aksi yang mengubah data (buat konten, setujui, posting, simpan profil) memerlukan **kunci API**
yang disimpan di browser. Isi lewat halaman **Pengaturan**; kunci dikirim sebagai header
`X-API-Key` hanya pada permintaan yang mengubah data.

## Design system

| Token | Nilai | Pemakaian |
| --- | --- | --- |
| Primary | `#58C4F5` | tombol utama, aksen, grafik |
| Primary hover | `#36AEE8` | hover/active tombol |
| Primary light | `#EAF8FF` | latar lembut, badge |
| Background | `#F7FAFD` | latar halaman |
| Surface | `#FFFFFF` | kartu, panel, topbar |
| Secondary | `#E8F1FA` | chip, skeleton, area redup |
| Text | `#243447` | teks utama |
| Muted text | `#64748B` | teks sekunder |
| Border | `#E2EAF2` | garis kartu dan pemisah |
| Success / Warning / Error | hijau / oranye / merah | status nyata dari backend |

Sudut membulat (`rounded-xl`/`rounded-2xl`), bayangan halus, spasi konsisten, tanpa gradien
berlebihan. Semua warna didefinisikan di `tailwind.config.js`, kelas komponen (`.card`, `.btn`,
`.input`, `.badge`) di `src/index.css`.

## Halaman

| Halaman | Isi |
| --- | --- |
| Dashboard | Sapaan, ringkasan aktivitas, statistik nyata, grafik metrik, status layanan, konten terbaru, rencana kalender, kabar terbaru, checklist persiapan akun. |
| Buat Konten | Form topik + contoh ide, pilihan Carousel/Reels, riset fakta, durasi, pratinjau hasil, persetujuan pose, editor caption Reels, aksi posting dengan konfirmasi, log proses AI (ringkas/teknis). |
| Riwayat Konten | Daftar konten dengan filter status, thumbnail, biaya, pesan kesalahan. |
| Kalender Strategi | Item 7 hari per tanggal, filter keputusan, setujui/tolak, buat konten dari item. |
| Asset Library | Grid pose dengan filter status, setujui/tolak, buat ulang pose, tautan ke konten. |
| Template Layout | Katalog 30 layout dengan filter peran dan pencarian. |
| Analitik | Ringkasan metrik, grafik per postingan, rekomendasi AI, tabel (desktop) / kartu (mobile). |
| Koneksi Sosial | Status nyata Instagram, penjadwal, Facebook (belum tersedia), akses API, publikasi terakhir, antrian kalender. |
| Brand & Aset | Identitas usaha, warna khas dengan validasi hex, unggah logo, unggah foto model. |
| Profil Enterprise | Profil, pilar konten, aturan brand, kelengkapan profil, produk, audiens, kepatuhan. |
| Pengaturan | Kunci API, status backend, data & privasi, tentang aplikasi. |

## Struktur

```
src/
  api.js                 # klien HTTP (kontrak backend tidak berubah)
  App.jsx                # shell aplikasi + state pipeline/polling
  components/
    ui.jsx               # Button, Card, Field, Modal, Badge, StatCard, Pills, dll.
    Sidebar.jsx Topbar.jsx NotificationBell.jsx ToastStack.jsx
    ContentPreview.jsx ActivityFeed.jsx Chart.jsx BrandIcons.jsx
  lib/
    format.js            # format tanggal/angka + label status bahasa Indonesia
    nav.js               # struktur navigasi + metadata halaman
    utils.js             # cn() helper
  pages/                 # satu file per halaman
```

## Responsif & aksesibilitas

- Diuji pada lebar 360, 390, 430, 768, 1024, dan 1440 px tanpa overflow horizontal.
- Sidebar berubah menjadi drawer dengan overlay di bawah 1024 px; menutup otomatis setelah navigasi.
- Tabel analitik berubah menjadi kartu di layar kecil.
- Target sentuh diperbesar pada perangkat `pointer: coarse`.
- Label form terhubung ke input, tombol ikon memiliki `aria-label`, dialog memakai `role="dialog"`
  dan dapat ditutup dengan Escape, tersedia tautan “Lewati ke konten utama”.

## Catatan kejujuran data

- Statistik hanya menampilkan angka dari API. Tidak ada data contoh buatan frontend.
- Metrik yang ditandai simulasi oleh backend diberi label “simulasi”.
- Fitur yang belum ada di backend (mis. publikasi Facebook) ditampilkan sebagai belum tersedia,
  bukan tombol palsu.
