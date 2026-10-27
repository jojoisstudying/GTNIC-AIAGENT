const API_BASE = '';

export const api = {
  getBrand: async () => {
    const res = await fetch(`${API_BASE}/api/v1/brand`);
    if (!res.ok) throw new Error('Gagal mengambil data brand');
    return res.json();
  },

  getLayouts: async () => {
    const res = await fetch(`${API_BASE}/api/v1/layouts`);
    if (!res.ok) throw new Error('Gagal mengambil daftar layout');
    return res.json();
  },

  // status: 'all' | 'pending_review' | 'approved' | 'rejected' (alias 'pending' juga diterima backend)
  getAssets: async (status = 'all') => {
    const qs = status && status !== 'all' ? `?status=${encodeURIComponent(status)}` : '';
    const res = await fetch(`${API_BASE}/api/v1/assets${qs}`);
    if (!res.ok) throw new Error('Gagal mengambil daftar asset');
    return res.json();
  },

  getRuns: async ({ limit = 30, offset = 0, status } = {}) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set('status', status);
    const res = await fetch(`${API_BASE}/api/v1/runs?${params}`);
    if (!res.ok) throw new Error('Gagal mengambil riwayat run');
    return res.json();
  },

  generateCarousel: async (topic, fresh = true) => {
    const res = await fetch(`${API_BASE}/api/v1/runs/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic, fresh, include_design: true })
    });
    if (!res.ok) throw new Error('Gagal memicu pembuatan carousel');
    return res.json();
  },

  generateVideo: async (topic, targetDuration = 30) => {
    const res = await fetch(`${API_BASE}/api/v1/runs/generate-video`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic, target_duration: targetDuration })
    });
    if (!res.ok) throw new Error('Gagal memicu pembuatan video');
    return res.json();
  },

  getRunStatus: async (runId) => {
    const res = await fetch(`${API_BASE}/api/v1/runs/${runId}`);
    if (!res.ok) throw new Error('Gagal mengambil status run');
    return res.json();
  },

  getRunEvents: async (runId) => {
    const res = await fetch(`${API_BASE}/api/v1/runs/${runId}/events`);
    if (!res.ok) throw new Error('Gagal mengambil event log');
    return res.json();
  },

  publishToInstagram: async (runId) => {
    const res = await fetch(`${API_BASE}/api/v1/runs/${runId}/publish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || data.error || 'Gagal publikasi ke Instagram');
    }
    return data;
  },

  updateBrand: async (brandData) => {
    const res = await fetch(`${API_BASE}/api/v1/brand`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(brandData)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Gagal memperbarui konfigurasi brand');
    }
    return res.json();
  },

  uploadLogo: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/v1/brand/logo`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Gagal mengupload logo');
    }
    return res.json();
  },

  uploadTalentReference: async (file, personId = 'operator_01') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('person_id', personId);
    const res = await fetch(`${API_BASE}/api/v1/assets/upload`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Gagal mengupload foto orang mentahan');
    }
    return res.json();
  },

  reviewAsset: async (assetId, status = 'approved') => {
    const res = await fetch(`${API_BASE}/api/v1/assets/${assetId}/review?status=${status}`, {
      method: 'POST'
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || `Gagal ${status} aset`);
    }
    return data;
  },

  // Buat ulang pose yang ditolak. Kalau run terkait sedang menunggu, backend melanjutkannya otomatis.
  regeneratePose: async (assetId, { runId = null, prompt = '' } = {}) => {
    const res = await fetch(`${API_BASE}/api/v1/assets/${assetId}/regenerate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId, prompt })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || 'Gagal membuat ulang pose');
    }
    return data;
  },

  resumeRun: async (runId) => {
    const res = await fetch(`${API_BASE}/api/v1/runs/${runId}/resume`, {
      method: 'POST'
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || 'Gagal melanjutkan pipeline');
    }
    return data;
  }
};