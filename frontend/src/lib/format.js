// Utilitas format & metadata label yang dipakai lintas halaman.

// started_at dari backend (SQLite) bisa tanpa suffix timezone; nilainya UTC
export const fmtTime = (iso) => {
  if (!iso) return '-';
  const withTz = /(Z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : `${iso}Z`;
  const date = new Date(withTz);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' });
};

export const fmtDateLong = (iso) => {
  if (!iso) return '-';
  const withTz = /(Z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : `${iso}Z`;
  const date = new Date(withTz);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString('id-ID', { dateStyle: 'long' });
};

export const fmtDayName = (isoDate) => {
  if (!isoDate) return '';
  const date = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString('id-ID', { weekday: 'long', timeZone: 'UTC' });
};

export const fmtNumber = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('id-ID');
};

export const fmtCompact = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  if (Math.abs(n) < 1000) return String(n);
  return new Intl.NumberFormat('id-ID', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
};

export const fmtMoney = (value, digits = 4) => `$${Number(value || 0).toFixed(digits)}`;

export const timeAgo = (iso) => {
  if (!iso) return '-';
  const withTz = /(Z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : `${iso}Z`;
  const then = new Date(withTz).getTime();
  if (Number.isNaN(then)) return '-';
  const diffSec = Math.round((Date.now() - then) / 1000);
  if (diffSec < 45) return 'baru saja';
  if (diffSec < 3600) return `${Math.round(diffSec / 60)} menit lalu`;
  if (diffSec < 86400) return `${Math.round(diffSec / 3600)} jam lalu`;
  if (diffSec < 604800) return `${Math.round(diffSec / 86400)} hari lalu`;
  return fmtTime(iso);
};

// ---------- Status run pipeline ----------
export const RUN_STATUS = {
  running: { label: 'Sedang diproses', tone: 'brand' },
  ok: { label: 'Selesai', tone: 'success' },
  awaiting_approval: { label: 'Menunggu persetujuan', tone: 'warning' },
  awaiting_assets: { label: 'Butuh foto pose', tone: 'warning' },
  failed: { label: 'Gagal', tone: 'danger' },
};

export const runStatusMeta = (status) =>
  RUN_STATUS[status] || { label: status ? String(status).replace(/_/g, ' ') : 'Tidak diketahui', tone: 'neutral' };

// ---------- Status aset ----------
export const ASSET_STATUS = {
  pending_review: { label: 'Menunggu review', tone: 'warning' },
  approved: { label: 'Disetujui', tone: 'success' },
  rejected: { label: 'Ditolak', tone: 'danger' },
  placeholder: { label: 'Placeholder', tone: 'neutral' },
  archived: { label: 'Diarsipkan', tone: 'neutral' },
  missing: { label: 'Tidak ditemukan', tone: 'danger' },
};

export const assetStatusMeta = (status) =>
  ASSET_STATUS[status] || { label: status || 'Tidak diketahui', tone: 'neutral' };

// ---------- Status item kalender strategi ----------
export const STRATEGY_STATUS = {
  draft: { label: 'Draft', tone: 'neutral' },
  awaiting_approval: { label: 'Menunggu persetujuan', tone: 'warning' },
  approved: { label: 'Disetujui', tone: 'success' },
  approved_to_publish: { label: 'Siap tayang', tone: 'success' },
  scheduled: { label: 'Terjadwal', tone: 'brand' },
  producing: { label: 'Sedang dibuat', tone: 'brand' },
  generation_failed: { label: 'Gagal dibuat', tone: 'danger' },
  publishing: { label: 'Sedang posting', tone: 'brand' },
  published: { label: 'Sudah tayang', tone: 'success' },
  publication_failed: { label: 'Gagal posting', tone: 'danger' },
  rejected: { label: 'Ditolak', tone: 'danger' },
};

export const strategyStatusMeta = (status) =>
  STRATEGY_STATUS[status] || { label: status || 'Tidak diketahui', tone: 'neutral' };

// ---------- Status publikasi ----------
export const publicationMeta = (status) => {
  if (status === 'published') return { label: 'Sudah tayang di Instagram', tone: 'success' };
  if (status === 'intent') return { label: 'Posting belum selesai', tone: 'warning' };
  if (status === 'failed' || status === 'error') return { label: 'Publikasi gagal', tone: 'danger' };
  return { label: status || 'Belum dipublikasikan', tone: 'neutral' };
};

// ---------- Label ramah untuk event pipeline ----------
const STEP_LABELS = {
  research: 'Riset fakta & tren',
  planner: 'Menyusun rencana konten',
  plan: 'Menyusun rencana konten',
  designer: 'Merancang visual slide',
  design: 'Merancang visual slide',
  qc: 'Pemeriksaan kualitas',
  render: 'Merender gambar',
  pose: 'Membuat pose foto',
  video: 'Merakit video',
  scriptwriter: 'Menulis naskah video',
  script: 'Menulis naskah video',
  tts: 'Membuat suara (voiceover)',
  broll: 'Menyiapkan cuplikan video',
  assemble: 'Menggabungkan video',
  publisher: 'Mempublikasikan ke Instagram',
  publish: 'Mempublikasikan ke Instagram',
  pricing: 'Menghitung biaya',
  strategy: 'Menyusun strategi',
  context: 'Menyiapkan konteks',
};

export const stepLabel = (step) => {
  if (!step) return 'Proses';
  return STEP_LABELS[String(step).toLowerCase()] || String(step).replace(/[_-]/g, ' ');
};

export const eventKindMeta = (kind) => {
  switch (kind) {
    case 'llm':
      return { label: 'AI menulis', tone: 'brand' };
    case 'tool':
      return { label: 'Alat bantu', tone: 'neutral' };
    case 'guardrail':
      return { label: 'Aturan brand', tone: 'warning' };
    case 'error':
      return { label: 'Kesalahan', tone: 'danger' };
    default:
      return { label: kind || 'Info', tone: 'neutral' };
  }
};

/** Ambil satu nilai ringkas dari payload event untuk ringkasan manusiawi. */
export const summarizeEvent = (event) => {
  const detail = event?.detail;
  if (!detail) return '';
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object') {
    const candidate = detail.summary || detail.message || detail.topic || detail.status || detail.error;
    if (typeof candidate === 'string') return candidate;
    try {
      return JSON.stringify(detail);
    } catch {
      return '';
    }
  }
  return String(detail);
};

export const truncate = (text, max = 120) => {
  const value = String(text ?? '');
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
};
