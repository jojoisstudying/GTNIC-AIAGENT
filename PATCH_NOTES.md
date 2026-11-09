# Patch notes
- api.py: generate dari kalender/autopilot pakai fresh=True; run riset harian tidak lagi menggantung 'running'; cooldown 30 menit untuk penyusunan strategi otomatis.
- automation_api.py (week_overview): status final (tayang/gagal/batal) tampil 30 hari; jam/tanggal memakai zona waktu pengaturan (WIB), bukan UTC; tidak lagi memotong item terbaru.
- core/scheduler.py: sync_and_automate menghormati Pause/Stop; log peringatan saat penjadwalan tertahan.
- core/strategy.py: anti-duplikat topik (30 hari) di prompt LLM dan fallback.
- core/automation.py: hitungan processed/failed diperbaiki.
Belum diubah: retry otomatis publikasi gagal sementara; riset per-run (masih file global).

## Putaran 2 (audit tombol)
- Pusat Otomatisasi: "Posting sekarang" tidak lagi muncul untuk konten yang belum disetujui (sebelumnya selalu error 409).
- "Coba produksi ulang" pada publikasi gagal diganti "Coba posting ulang" dan memberi jadwal baru (sebelumnya ditolak backend bila jadwal lama sudah lewat); persetujuan ulang mereset hitungan percobaan (sebelumnya terblokir selamanya setelah 3x gagal).
- "Ubah jadwal"/"Ubah topik" hanya tampil bila berefek (tidak untuk gagal/batal/ditolak/tayang, atau topik yang sudah punya hasil).
- Kalender Strategi: item "ditolak" (termasuk akibat pembatalan publikasi) sekarang bisa dipulihkan ke draf; sebelumnya jalan buntu.
Belum ditangani: 4 fungsi api.js tidak dipakai (getInstagramStatus, getPublications, getRunPublication, preparePublication); API kampanye (/campaigns*) tanpa UI; blok tombol draft/awaiting_approval di Strategy.jsx duplikat; reschedule publikasi memakai offset +07:00 hardcode.
