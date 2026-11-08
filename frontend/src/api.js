// Alamat backend bisa dipisah dari frontend lewat VITE_API_BASE_URL (mis. saat
// frontend di-hosting statis dan API berjalan di server lain). Kosong = origin
// yang sama, memakai proxy Vite saat `npm run dev` atau backend yang menyajikan
// folder dist.
const RAW_API_BASE = (import.meta.env.VITE_API_BASE_URL || '').trim();
const API_BASE = RAW_API_BASE.replace(/\/+$/, '');
const API_KEY_STORAGE = 'gtnic-api-key';

const protectedHeaders = (headers = {}) => {
  const key = window.localStorage.getItem(API_KEY_STORAGE);
  const user = window.localStorage.getItem('gtnic_user_name');
  return { ...headers, ...(key ? { 'X-API-Key': key } : {}), ...(user ? { 'X-User-Name': user } : {}) };
};

const readError = async (res, fallback) => {
  const data = await res.json().catch(() => ({}));
  const detail = typeof data.detail === 'string'
    ? data.detail
    : Array.isArray(data.detail) && data.detail[0]?.msg
      ? data.detail[0].msg
      : data.error;
  const message = detail || fallback;
  return new Error(res.status ? `${message} (HTTP ${res.status})` : message);
};

// fetch yang membedakan "backend tidak bisa dihubungi" dari error HTTP biasa,
// supaya toast tidak hanya menampilkan pesan generik.
const request = async (path, options = {}) => {
  const mergedHeaders = protectedHeaders(options.headers || {});
  const mergedOptions = { ...options, headers: mergedHeaders };
  try {
    return await fetch(`${API_BASE}${path}`, mergedOptions);
  } catch (err) {
    // AbortError bukan kegagalan koneksi: teruskan apa adanya supaya pemanggil bisa
    // membedakan "dibatalkan pengguna" dari "backend tidak bisa dihubungi".
    if (err?.name === 'AbortError') throw err;
    const target = API_BASE || window.location.origin;
    throw new Error(
      `Tidak bisa menghubungi backend di ${target}. Pastikan API berjalan `
      + 'dan VITE_API_BASE_URL mengarah ke alamat yang benar.'
    );
  }
};

export const api = {
  getBrand: async () => {
    const res = await request('/api/v1/brand');
    if (!res.ok) throw await readError(res, 'Gagal mengambil data brand');
    return res.json();
  },

  getLayouts: async () => {
    const res = await request('/api/v1/layouts');
    if (!res.ok) throw await readError(res, 'Gagal mengambil daftar layout');
    return res.json();
  },

  // status: 'all' | 'pending_review' | 'approved' | 'rejected' (alias 'pending' juga diterima backend)
  getAssets: async (status = 'all') => {
    const qs = status && status !== 'all' ? `?status=${encodeURIComponent(status)}` : '';
    const res = await request(`/api/v1/assets${qs}`);
    if (!res.ok) throw await readError(res, 'Gagal mengambil daftar asset');
    return res.json();
  },

  getRuns: async ({ limit = 30, offset = 0, status } = {}) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set('status', status);
    const res = await request(`/api/v1/runs?${params}`);
    if (!res.ok) throw await readError(res, 'Gagal mengambil riwayat run');
    return res.json();
  },

  generateCarousel: async (topic, fresh = true, signal) => {
    const res = await request('/api/v1/runs/generate', {
      method: 'POST',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ topic, fresh, include_design: true }),
      ...(signal ? { signal } : {}),
    });
    if (!res.ok) throw await readError(res, 'Gagal memicu pembuatan carousel');
    return res.json();
  },

  generateVideo: async (topic, targetDuration = 30, fresh = true, signal) => {
    const res = await request('/api/v1/runs/generate-video', {
      method: 'POST',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ topic, target_duration: targetDuration, fresh }),
      ...(signal ? { signal } : {}),
    });
    if (!res.ok) throw await readError(res, 'Gagal memicu pembuatan video');
    return res.json();
  },

  getRunStatus: async (runId) => {
    const res = await request(`/api/v1/runs/${runId}`);
    if (!res.ok) throw await readError(res, 'Gagal mengambil status run');
    return res.json();
  },

  getRunEvents: async (runId) => {
    const res = await request(`/api/v1/runs/${runId}/events`);
    if (!res.ok) throw await readError(res, 'Gagal mengambil event log');
    return res.json();
  },

  // options (khusus Reels): { caption, share_to_feed }
  publishToInstagram: async (runId, options) => {
    const res = await request(`/api/v1/runs/${runId}/publish`, {
      method: 'POST',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      ...(options ? { body: JSON.stringify(options) } : {})
    });
    if (!res.ok) throw await readError(res, 'Gagal publikasi ke Instagram');
    return res.json();
  },

  updateBrand: async (brandData) => {
    const res = await request('/api/v1/brand', {
      method: 'POST',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(brandData)
    });
    if (!res.ok) throw await readError(res, 'Gagal memperbarui konfigurasi brand');
    return res.json();
  },

  uploadLogo: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await request('/api/v1/brand/logo', {
      method: 'POST',
      headers: protectedHeaders(),
      body: formData
    });
    if (!res.ok) throw await readError(res, 'Gagal mengupload logo');
    return res.json();
  },

  uploadTalentReference: async (file, personId = 'operator_01') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('person_id', personId);
    const res = await request('/api/v1/assets/upload', {
      method: 'POST',
      headers: protectedHeaders(),
      body: formData
    });
    if (!res.ok) throw await readError(res, 'Gagal mengupload foto orang mentahan');
    return res.json();
  },

  reviewAsset: async (assetId, status = 'approved') => {
    const res = await request(`/api/v1/assets/${assetId}/review?status=${status}`, {
      method: 'POST',
      headers: protectedHeaders(),
    });
    if (!res.ok) throw await readError(res, `Gagal ${status} aset`);
    return res.json();
  },

  // Buat ulang pose yang ditolak. Kalau run terkait sedang menunggu, backend melanjutkannya otomatis.
  regeneratePose: async (assetId, { runId = null, prompt = '' } = {}) => {
    const res = await request(`/api/v1/assets/${assetId}/regenerate`, {
      method: 'POST',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ run_id: runId, prompt })
    });
    if (!res.ok) throw await readError(res, 'Gagal membuat ulang pose');
    return res.json();
  },

  resumeRun: async (runId) => {
    const res = await request(`/api/v1/runs/${runId}/resume`, {
      method: 'POST',
      headers: protectedHeaders(),
    });
    if (!res.ok) throw await readError(res, 'Gagal melanjutkan pipeline');
    return res.json();
  },

  // FEATURE-01: Enterprise Profile & Onboarding
  getEnterpriseProfile: async () => {
    const res = await request('/api/v1/enterprise/profile');
    if (!res.ok) throw await readError(res, 'Gagal mengambil profil enterprise');
    return res.json();
  },

  updateEnterpriseProfile: async (profileData) => {
    const res = await request('/api/v1/enterprise/profile', {
      method: 'PUT',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(profileData)
    });
    if (!res.ok) throw await readError(res, 'Gagal memperbarui profil enterprise');
    return res.json();
  },

  // FEATURE-02: Strategy Calendar & Approvals
  getStrategyCalendar: async (regenerate = false) => {
    const res = await request(`/api/v1/strategy/calendar?regenerate=${regenerate}`);
    if (!res.ok) throw await readError(res, 'Gagal mengambil kalender strategi');
    return res.json();
  },

  // Backend memisahkan regenerate ke POST; GET hanya membaca (dan membuat kalender bila kosong).
  regenerateStrategyCalendar: async () => {
    const res = await request('/api/v1/strategy/calendar/regenerate', {
      method: 'POST',
      headers: protectedHeaders(),
    });
    if (!res.ok) throw await readError(res, 'Gagal membuat ulang kalender strategi');
    return res.json();
  },

  updateStrategyItem: async (itemId, action) => {
    const res = await request(`/api/v1/strategy/calendar/${itemId}`, {
      method: 'PATCH',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(action)
    });
    if (!res.ok) throw await readError(res, 'Gagal memperbarui item strategi');
    return res.json();
  },

  generateFromStrategyItem: async (itemId) => {
    const res = await request(`/api/v1/strategy/calendar/${itemId}/generate`, {
      method: 'POST',
      headers: protectedHeaders(),
    });
    if (!res.ok) throw await readError(res, 'Gagal menjalankan pipeline dari strategi');
    return res.json();
  },

  // FEATURE-03: Analytics & Feedback Loop
  getAnalyticsDashboard: async () => {
    const res = await request('/api/v1/analytics/dashboard');
    if (!res.ok) throw await readError(res, 'Gagal mengambil data analytics dashboard');
    return res.json();
  },

  // Operations Center (notifikasi, audit, status operasional)
  getOpsStatus: async () => {
    const res = await request('/api/v1/ops/status');
    if (!res.ok) throw await readError(res, 'Gagal mengambil status operasional');
    return res.json();
  },

  getNotifications: async ({ unreadOnly = false, limit = 20 } = {}) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (unreadOnly) params.set('unread_only', 'true');
    const res = await request(`/api/v1/notifications?${params}`);
    if (!res.ok) throw await readError(res, 'Gagal mengambil notifikasi');
    return res.json();
  },

  readNotification: async (id) => {
    const res = await request(`/api/v1/notifications/${id}/read`, {
      method: 'POST',
      headers: protectedHeaders(),
    });
    if (!res.ok) throw await readError(res, 'Gagal menandai notifikasi');
    return res.json();
  },

  readAllNotifications: async () => {
    const res = await request('/api/v1/notifications/read-all', {
      method: 'POST',
      headers: protectedHeaders(),
    });
    if (!res.ok) throw await readError(res, 'Gagal menandai semua notifikasi');
    return res.json();
  },

  // ---- Alur persetujuan publikasi (Pusat Otomatisasi & preview konten) ----
  // Siapkan draf publikasi untuk sebuah run. Backend TIDAK memanggil Instagram di sini.
  preparePublication: async (runId, options = {}) => {
    const res = await request(`/api/v1/runs/${runId}/publication`, {
      method: 'POST',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(options),
    });
    if (!res.ok) throw await readError(res, 'Gagal menyiapkan draf publikasi');
    return res.json();
  },

  getRunPublication: async (runId) => {
    const res = await request(`/api/v1/runs/${runId}/publication`);
    if (!res.ok) throw await readError(res, 'Gagal mengambil status publikasi');
    return res.json();
  },

  // Edit caption/hashtag/gambar/jadwal sebelum disetujui.
  updatePublication: async (pubId, patch) => {
    const res = await request(`/api/v1/publications/${pubId}`, {
      method: 'PATCH',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(patch),
    });
    if (!res.ok) throw await readError(res, 'Gagal menyimpan perubahan konten');
    return res.json();
  },

  // Setujui & Publikasikan (idempoten di backend; aman bila tombol terklik dua kali).
  approvePublication: async (pubId, options = {}) => {
    const res = await request(`/api/v1/publications/${pubId}/approve`, {
      method: 'POST',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(options),
    });
    if (!res.ok) throw await readError(res, 'Gagal menyetujui publikasi');
    return res.json();
  },

  publishPublication: async (pubId) => {
    const res = await request(`/api/v1/publications/${pubId}/publish`, {
      method: 'POST',
      headers: protectedHeaders(),
    });
    if (!res.ok) throw await readError(res, 'Gagal mempublikasikan konten');
    return res.json();
  },

  cancelPublication: async (pubId) => {
    const res = await request(`/api/v1/publications/${pubId}/cancel`, {
      method: 'POST',
      headers: protectedHeaders(),
    });
    if (!res.ok) throw await readError(res, 'Gagal membatalkan publikasi');
    return res.json();
  },

  // Setujui semua sekaligus: publikasi menunggu + ide kalender. TIDAK memanggil API Meta —
  // konten hanya disetujui & dijadwalkan, scheduler yang menayangkan.
  approveAllPublications: async (options = {}) => {
    const res = await request('/api/v1/publications/approve-all', {
      method: 'POST',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(options),
    });
    if (!res.ok) throw await readError(res, 'Gagal menyetujui semua konten');
    return res.json();
  },

  getPublications: async ({ status, limit = 50 } = {}) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (status) params.set('status', status);
    const res = await request(`/api/v1/publications?${params}`);
    if (!res.ok) throw await readError(res, 'Gagal mengambil daftar publikasi');
    return res.json();
  },

  getPublication: async (pubId) => {
    const res = await request(`/api/v1/publications/${pubId}`);
    if (!res.ok) throw await readError(res, 'Gagal mengambil detail publikasi');
    return res.json();
  },

  // Batalkan generasi konten yang sedang berjalan (tidak menyimpan hasil yang dibatalkan).
  cancelRun: async (runId) => {
    const res = await request(`/api/v1/runs/${runId}/cancel`, {
      method: 'POST',
      headers: protectedHeaders(),
    });
    if (!res.ok) throw await readError(res, 'Gagal membatalkan proses pembuatan konten');
    return res.json();
  },

  // ---- Pusat Otomatisasi ----
  getAutomation: async () => {
    const res = await request('/api/v1/automation');
    if (!res.ok) throw await readError(res, 'Gagal mengambil pengaturan otomatisasi');
    return res.json();
  },

  updateAutomation: async (patch) => {
    const res = await request('/api/v1/automation', {
      method: 'PUT',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(patch),
    });
    if (!res.ok) throw await readError(res, 'Gagal menyimpan pengaturan otomatisasi');
    return res.json();
  },

  automationControl: async (action) => {
    const res = await request(`/api/v1/automation/${action}`, {
      method: 'POST',
      headers: protectedHeaders(),
    });
    if (!res.ok) throw await readError(res, `Gagal menjalankan ${action}`);
    return res.json();
  },

  // ---- Analytics per konten ----
  getAnalyticsPublications: async () => {
    const res = await request('/api/v1/analytics/publications');
    if (!res.ok) throw await readError(res, 'Gagal mengambil daftar konten terpantau');
    return res.json();
  },

  getPublicationAnalytics: async (pubId) => {
    const res = await request(`/api/v1/analytics/publications/${pubId}`);
    if (!res.ok) throw await readError(res, 'Gagal mengambil metrik konten');
    return res.json();
  },

  ingestMetrics: async (publicationId = null) => {
    const res = await request('/api/v1/analytics/publications/ingest', {
      method: 'POST',
      headers: protectedHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(publicationId ? { publication_id: publicationId } : {}),
    });
    if (!res.ok) throw await readError(res, 'Gagal mengambil metrik dari Instagram');
    return res.json();
  },

  // ---- Diagnostik integrasi Instagram ----
  getInstagramStatus: async () => {
    const res = await request('/api/v1/integrations/instagram/status');
    if (!res.ok) throw await readError(res, 'Gagal memeriksa koneksi Instagram');
    return res.json();
  },

  getHealth: async () => {
    const res = await request('/api/v1/health');
    if (!res.ok) throw await readError(res, 'Backend tidak merespons');
    return res.json();
  },

  // Server memberi tahu apakah header X-API-Key diwajibkan pada konfigurasi ini.
  getAuthStatus: async () => {
    const res = await request('/api/v1/auth/status');
    if (!res.ok) throw await readError(res, 'Gagal membaca status autentikasi');
    return res.json();
  },

  // Khusus mode lokal: backend mengirim kunci API-nya sendiri untuk UI di mesin
  // yang sama (loopback + non-production), supaya tidak perlu tempel manual.
  getDevApiKey: async () => {
    const res = await request('/api/v1/auth/dev-key');
    if (!res.ok) return '';
    const data = await res.json().catch(() => ({}));
    return data.api_key || '';
  },

  getApiKey: () => window.localStorage.getItem(API_KEY_STORAGE) || '',

  setApiKey: (key) => {
    if (key?.trim()) window.localStorage.setItem(API_KEY_STORAGE, key.trim());
    else window.localStorage.removeItem(API_KEY_STORAGE);
  },
};
