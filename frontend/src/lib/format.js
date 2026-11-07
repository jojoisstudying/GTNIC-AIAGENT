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
  cancelled: { label: 'Dibatalkan', tone: 'neutral' },
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

// ---------- Status alur persetujuan publikasi ----------
// Sumber label: backend (status_label), tetapi UI perlu tone warna & ikon yang konsisten.
export const PUBLICATION_STATUS = {
  pending_approval: { label: 'Menunggu persetujuan', tone: 'warning', icon: 'clock' },
  scheduled: { label: 'Dijadwalkan', tone: 'brand', icon: 'calendar' },
  publishing: { label: 'Sedang dipublikasikan', tone: 'brand', icon: 'loader' },
  intent: { label: 'Status belum pasti', tone: 'warning', icon: 'alert' },
  published: { label: 'Berhasil', tone: 'success', icon: 'check' },
  failed: { label: 'Gagal', tone: 'danger', icon: 'x' },
  cancelled: { label: 'Dibatalkan', tone: 'neutral', icon: 'ban' },
};

export const publicationStatusMeta = (status) =>
  PUBLICATION_STATUS[status] || {
    label: status ? String(status).replace(/_/g, ' ') : 'Tidak diketahui',
    tone: 'neutral',
    icon: 'info',
  };

// Status otomatisasi (Pusat Otomatisasi)
export const AUTOMATION_STATE = {
  running: { label: 'Berjalan', tone: 'success' },
  paused: { label: 'Dijeda', tone: 'warning' },
  stopped: { label: 'Dihentikan', tone: 'neutral' },
};

export const automationStateMeta = (state) =>
  AUTOMATION_STATE[state] || { label: state || 'Tidak diketahui', tone: 'neutral' };

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

/**
 * Terjemahkan error backend yang sering muncul menjadi langkah perbaikan
 * yang bisa langsung dijalankan operator. Mengembalikan null bila tidak ada
 * padanan yang diketahui (biarkan pesan asli tampil apa adanya).
 */
export const runErrorHint = (error) => {
  const text = String(error ?? '');
  if (!text) return null;
  if (/too large for model|tokens per minute|TPM/i.test(text)) {
    return 'Permintaan AI melebihi batas token per menit (TPM) akun Groq. Prompt sudah diringkas otomatis; tunggu ±1 menit lalu jalankan lagi. Bila sering terjadi, turunkan LLM_MAX_COMPLETION_TOKENS atau isi LLM_TPM_LIMIT di backend/.env.';
  }
  if (/RequestTooLarge/i.test(text)) {
    return 'Permintaan AI melebihi batas token penyedia. Tunggu ±1 menit lalu jalankan lagi; prompt akan diringkas lebih agresif.';
  }
  if (/cooling down|rate limit exceeded|429/i.test(text)) {
    return 'Kuota penyedia AI sedang cooldown karena batas laju (rate limit). Tunggu sekitar 1 menit lalu jalankan lagi.';
  }
  if (/tool call|tool_use_failed/i.test(text)) {
    return 'Model AI beberapa kali mengirim tool call yang tidak valid. Coba jalankan lagi; kalau berulang, set GROQ_MODEL=openai/gpt-oss-120b di backend/.env lalu restart backend.';
  }
  if (/Chromium|playwright install/i.test(text)) {
    return 'Browser render belum terpasang di server. Jalankan: .\\.venv\\Scripts\\python.exe -m playwright install chromium di folder backend.';
  }
  if (/No API keys configured for provider '?groq'?/i.test(text) || /ProviderExhausted.*groq/i.test(text)) {
    return 'Kunci Groq belum ada. Isi GROQ_API_KEY di backend/.env lalu restart backend. Kunci gratis: https://console.groq.com/keys';
  }
  if (/No API keys configured for provider '?tavily'?/i.test(text)) {
    return 'Kunci Tavily belum ada. Isi TAVILY_API_KEY di backend/.env lalu restart backend. Kunci gratis: https://app.tavily.com';
  }
  if (/No API keys configured/i.test(text)) {
    return 'Kunci penyedia AI belum diisi di backend/.env. Isi GROQ_API_KEY (dan TAVILY_API_KEY untuk riset) lalu restart backend.';
  }
  if (/research_latest\.json belum ada/i.test(text)) {
    return 'Belum ada cache riset. Aktifkan "Riset web terbaru" di form generator, atau jalankan sekali dengan riset baru.';
  }
  if (/IG_TOKEN|Instagram/i.test(text)) {
    return 'Kredensial Instagram belum diatur di backend/.env (IG_TOKEN, IG_USER_ID).';
  }
  return null;
};

