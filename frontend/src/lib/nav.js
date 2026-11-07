import {
  BarChart3,
  Bot,
  Building2,
  CalendarDays,
  History,
  Image as ImageIcon,
  LayoutDashboard,
  Layers,
  Palette,
  Settings,
  Share2,
  Sparkles,
} from 'lucide-react';

export const NAV_GROUPS = [
  {
    label: 'Ringkasan',
    items: [{ key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard }],
  },
  {
    label: 'Konten',
    items: [
      { key: 'generator', label: 'Buat Konten', icon: Sparkles, hint: 'AI carousel & video' },
      { key: 'automation', label: 'Pusat Otomatisasi', icon: Bot, badge: 'pendingApprovals' },
      { key: 'runs', label: 'Riwayat Konten', icon: History, badge: 'pendingRuns' },
      { key: 'strategy', label: 'Kalender Strategi', icon: CalendarDays },
      { key: 'assets', label: 'Asset Library', icon: ImageIcon, badge: 'pendingAssets' },
      { key: 'layouts', label: 'Template Layout', icon: Layers },
    ],
  },
  {
    label: 'Pertumbuhan',
    items: [
      { key: 'analytics', label: 'Analitik', icon: BarChart3 },
      { key: 'social', label: 'Koneksi Sosial', icon: Share2 },
    ],
  },
  {
    label: 'Pengaturan',
    items: [
      { key: 'brand', label: 'Brand & Aset', icon: Palette },
      { key: 'enterprise', label: 'Profil Enterprise', icon: Building2 },
      { key: 'settings', label: 'Pengaturan', icon: Settings },
    ],
  },
];

export const PAGE_META = {
  dashboard: {
    title: 'Dashboard',
    description: 'Ringkasan aktivitas pemasaran, status konten, dan performa media sosial Anda.',
  },
  generator: {
    title: 'Buat Konten',
    description: 'Ubah satu topik menjadi carousel Instagram atau video Reels siap posting dengan bantuan AI.',
  },
  runs: {
    title: 'Riwayat Konten',
    description: 'Semua konten yang pernah dibuat beserta status terakhirnya.',
  },
  strategy: {
    title: 'Kalender Strategi',
    description: 'Rencana konten 7 hari ke depan yang bisa Anda setujui sebelum dibuat.',
  },
  assets: {
    title: 'Asset Library',
    description: 'Pustaka foto dan pose yang dipakai untuk merancang konten Anda.',
  },
  layouts: {
    title: 'Template Layout',
    description: 'Desain layout yang tersedia untuk menyusun setiap slide carousel.',
  },
  analytics: {
    title: 'Analitik',
    description: 'Ukur performa konten dan lihat rekomendasi untuk konten berikutnya.',
  },
  automation: {
    title: 'Pusat Otomatisasi',
    description: 'Kendalikan seluruh aktivitas marketing otomatis: jadwal, platform, jenis konten, dan persetujuan.',
  },
  social: {
    title: 'Koneksi Sosial',
    description: 'Status koneksi Instagram, penjadwalan, dan riwayat publikasi.',
  },
  brand: {
    title: 'Brand & Aset',
    description: 'Identitas usaha, warna khas, logo, dan foto model untuk konten Anda.',
  },
  enterprise: {
    title: 'Profil Enterprise',
    description: 'Konteks resmi usaha yang jadi dasar AI menyusun konten.',
  },
  settings: {
    title: 'Pengaturan',
    description: 'Kunci akses API, status layanan, dan informasi aplikasi.',
  },
};
