import React, { useState, useEffect, useRef } from 'react';
import { 
  Sparkles, 
  Layers, 
  Video, 
  Send, 
  Terminal, 
  CheckCircle2, 
  AlertCircle, 
  Clock, 
  Eye, 
  ChevronLeft, 
  ChevronRight, 
  Share2, 
  DollarSign, 
  Zap, 
  RefreshCw,
  FolderOpen,
  Image as ImageIcon,
  Cpu,
  Settings,
  Upload,
  Phone,
  Palette,
  Check,
  UserCheck,
  Download,
  Film,
  History
} from 'lucide-react';
import { api } from './api';

// started_at dari backend (SQLite) bisa tanpa suffix timezone; nilainya UTC
const fmtTime = (iso) => {
  if (!iso) return '-';
  const withTz = /(Z|[+-]\d\d:?\d\d)$/i.test(iso) ? iso : `${iso}Z`;
  return new Date(withTz).toLocaleString('id-ID', { dateStyle: 'short', timeStyle: 'short' });
};

const RUN_STATUS_STYLE = {
  ok: 'bg-emerald-950 text-emerald-400 border-emerald-800',
  running: 'bg-amber-950 text-amber-400 border-amber-800 animate-pulse',
  awaiting_approval: 'bg-amber-950 text-amber-300 border-amber-700',
  awaiting_assets: 'bg-orange-950 text-orange-300 border-orange-800',
  failed: 'bg-red-950 text-red-400 border-red-800'
};

const ASSET_FILTERS = [
  { key: 'pending_review', label: 'Menunggu Review' },
  { key: 'approved', label: 'Disetujui' },
  { key: 'rejected', label: 'Ditolak' },
  { key: 'all', label: 'Semua' }
];

export default function App() {
  // Navigation / Tabs: 'generator' | 'assets' | 'layouts' | 'brand_settings'
  const [activeTab, setActiveTab] = useState('generator');

  // Input states
  const [topic, setTopic] = useState('5 Strategi Kelola Cashflow Usaha Menghadapi Inflasi 2026');
  const [formatType, setFormatType] = useState('carousel'); // 'carousel' | 'video'
  const [targetDuration, setTargetDuration] = useState(30);
  const [freshResearch, setFreshResearch] = useState(true);

  // Execution & Polling states
  const [currentRunId, setCurrentRunId] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [runData, setRunData] = useState(null);
  const [events, setEvents] = useState([]);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState(null);

  // Carousel Preview slider
  const [currentSlideIndex, setCurrentSlideIndex] = useState(0);

  // Catalog / Brand states
  const [brand, setBrand] = useState(null);
  const [layouts, setLayouts] = useState([]);
  const [assets, setAssets] = useState([]);
  const [assetFilter, setAssetFilter] = useState('all');
  const [assetCounts, setAssetCounts] = useState({});
  const assetFilterTouched = useRef(false);
  const assetsInitialized = useRef(false);

  // Riwayat run
  const [runs, setRuns] = useState([]);
  const [runsFilter, setRunsFilter] = useState('all'); // 'all' | 'awaiting_approval'
  const [pendingRunsCount, setPendingRunsCount] = useState(0);

  // Brand Form states
  const [brandForm, setBrandForm] = useState({
    company: '',
    industry: '',
    description: '',
    phone: '',
    handle: '',
    primary_color: '#0f172a',
    secondary_color: '#f8fafc',
    accent_color: '#10b981'
  });
  const [brandSaving, setBrandSaving] = useState(false);
  const [logoUploading, setLogoUploading] = useState(false);
  const [talentUploading, setTalentUploading] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);

  // Auto-scroll log
  const logEndRef = useRef(null);

  const fetchBrand = () => {
    api.getBrand().then(b => {
      setBrand(b);
      const lines = b.chrome?.footer?.lines || [];
      setBrandForm({
        company: b.company || '',
        industry: b.industry || '',
        description: b.description || '',
        phone: lines[1] || '',
        handle: lines[0] || '',
        primary_color: b.colors?.primary || '#0f172a',
        secondary_color: b.colors?.secondary || '#f8fafc',
        accent_color: b.colors?.accent || '#10b981'
      });
    }).catch(console.error);
  };

  const fetchAssets = (filter = assetFilter) => {
    api.getAssets(filter).then(res => {
      setAssets(res.assets || []);
      setAssetCounts(res.counts || {});
      // Pertama kali dibuka: kalau ada yang menunggu review, langsung tampilkan itu
      if (!assetsInitialized.current) {
        assetsInitialized.current = true;
        if (!assetFilterTouched.current && filter === 'all' && (res.counts?.pending_review || 0) > 0) {
          setAssetFilter('pending_review');
        }
      }
    }).catch(console.error);
  };

  const changeAssetFilter = (key) => {
    assetFilterTouched.current = true;
    setAssetFilter(key);
  };

  const fetchRuns = () => {
    api.getRuns({ limit: 50, status: runsFilter === 'awaiting_approval' ? 'awaiting_approval' : undefined })
      .then(res => setRuns(res.runs || []))
      .catch(console.error);
    api.getRuns({ limit: 1, status: 'awaiting_approval' })
      .then(res => setPendingRunsCount(res.total || 0))
      .catch(console.error);
  };

  // Inisialisasi data awal (Brand, Layouts)
  useEffect(() => {
    fetchBrand();
    api.getLayouts().then(res => setLayouts(res.layouts || [])).catch(console.error);
  }, []);

  // Asset list mengikuti filter (fetch awal juga lewat sini)
  useEffect(() => {
    fetchAssets(assetFilter);
  }, [assetFilter]);

  // Riwayat run: muat ulang saat filter berubah, tab dibuka, atau sebuah run selesai
  useEffect(() => {
    fetchRuns();
  }, [isRunning, runsFilter, activeTab]);

  // Polling status run & events saat isRunning == true
  useEffect(() => {
    if (!currentRunId) return;

    let cancelled = false;
    let interval = null;
    const poll = async () => {
      try {
        const [statusRes, eventsRes] = await Promise.all([
          api.getRunStatus(currentRunId),
          api.getRunEvents(currentRunId)
        ]);
        if (cancelled) return;
        setRunData(statusRes);
        setEvents(eventsRes.events || []);

        if (['ok', 'failed', 'awaiting_approval', 'awaiting_assets'].includes(statusRes.status)) {
          setIsRunning(false);
          clearInterval(interval);
        }
      } catch (err) {
        if (!cancelled) console.error('Polling error:', err);
      }
    };

    poll(); // Jalankan sekali langsung
    if (isRunning) {
      interval = setInterval(poll, 1500);
    }

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [currentRunId, isRunning]);

  // Auto scroll terminal log ke bawah
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  // Trigger pembuatan konten baru
  const handleGenerate = async (e) => {
    e.preventDefault();
    if (!topic.trim()) return;

    setCurrentRunId(null); 
    setIsRunning(true);
    setRunData(null);
    setEvents([]);
    setCurrentSlideIndex(0);
    setPublishResult(null);

    try {
      let res;
      if (formatType === 'carousel') {
        res = await api.generateCarousel(topic, freshResearch);
      } else {
        res = await api.generateVideo(topic, targetDuration, freshResearch);
      }
      setCurrentRunId(res.run_id);
    } catch (err) {
      alert(`Error: ${err.message}`);
      setIsRunning(false);
    }
  };

  // Publish ke Instagram
  const handlePublish = async () => {
    if (!currentRunId) return;
    setPublishing(true);
    setPublishResult(null);
    try {
      const res = await api.publishToInstagram(currentRunId);
      setPublishResult(res);
      // Refresh event log to include publisher audit events
      try {
        const eventsRes = await api.getRunEvents(currentRunId);
        setEvents(eventsRes.events || []);
      } catch (e) {
        console.error(e);
      }
      const isOk = res.status === 'published' || res.ok;
      alert(isOk ? 'Berhasil dikirim ke Instagram!' : `Gagal: ${res.error || 'Terjadi kesalahan'}`);
    } catch (err) {
      alert(`Publikasi gagal: ${err.message}`);
    } finally {
      setPublishing(false);
    }
  };

  // Save Brand Configuration
  const [approvingAssetId, setApprovingAssetId] = useState(null);
  const [regeneratingId, setRegeneratingId] = useState(null);
  const [resumingRun, setResumingRun] = useState(false);

  // Muat ulang status & event satu run (dipakai saat membuka run lama / setelah review)
  const refreshRun = async (runId) => {
    const [statusRes, eventsRes] = await Promise.all([api.getRunStatus(runId), api.getRunEvents(runId)]);
    setRunData(statusRes);
    setEvents(eventsRes.events || []);
    return statusRes;
  };

  // Buka run lama dari riwayat / daftar aset (termasuk yang masih awaiting_approval)
  const openRun = async (runId, format, status) => {
    setCurrentRunId(runId);
    setRunData(null);
    setEvents([]);
    setCurrentSlideIndex(0);
    setPublishResult(null);
    if (format) setFormatType(format);
    setIsRunning(status === 'running');
    setActiveTab('generator');
    window.scrollTo({ top: 0, behavior: 'smooth' });
    try {
      const fresh = await refreshRun(runId); // effect polling tidak jalan ulang kalau run_id-nya sama
      if (fresh.status === 'running') setIsRunning(true);
    } catch (err) {
      setStatusMessage({ type: 'error', text: `Gagal membuka run: ${err.message}` });
    }
  };

  // Approve / reject pose. Run dilanjutkan otomatis hanya jika SEMUA pose run itu sudah
  // diputuskan dan tidak ada yang ditolak (reject butuh regenerate, lihat #10).
  const handleApproveAsset = async (assetId, decision = 'approved', assetRunId = null) => {
    setApprovingAssetId(assetId);
    try {
      await api.reviewAsset(assetId, decision);
      fetchAssets();
      fetchRuns();

      const targetRunId = assetRunId || currentRunId;
      const isCurrent = targetRunId && targetRunId === currentRunId;
      let text = `Asset pose ID ${assetId} berhasil di-${decision === 'approved' ? 'setujui' : 'tolak'}.`;

      if (isCurrent) {
        const fresh = await refreshRun(targetRunId);
        const items = fresh.design?.pending_review || [];
        const waiting = ['awaiting_approval', 'awaiting_assets'].includes(fresh.status);
        const stillPending = items.some(i => i.status === 'pending_review');
        const anyRejected = items.some(i => i.status === 'rejected');
        if (waiting && items.length > 0 && !stillPending && !anyRejected) {
          setResumingRun(true);
          await api.resumeRun(targetRunId);
          setIsRunning(true);
          text += ' Semua pose sudah disetujui, melanjutkan rendering...';
        } else if (stillPending) {
          text += ` Masih ada ${items.filter(i => i.status === 'pending_review').length} pose yang menunggu keputusan.`;
        } else if (anyRejected) {
          text += ' Ada pose yang ditolak, run belum bisa dilanjutkan.';
        }
      } else if (targetRunId) {
        text += ' Buka run terkait dari tab Riwayat Run untuk melanjutkannya.';
      }
      setStatusMessage({ type: 'success', text });
    } catch (err) {
      setStatusMessage({ type: 'error', text: `Gagal review aset: ${err.message}` });
    } finally {
      setApprovingAssetId(null);
      setResumingRun(false);
    }
  };

  // Buat ulang pose yang ditolak. Jika run terkait menunggu, backend generate lalu resume otomatis
  const handleRegenerate = async (assetId, assetRunId = null) => {
    setRegeneratingId(assetId);
    try {
      const targetRunId = assetRunId || currentRunId;
      const res = await api.regeneratePose(assetId, { runId: targetRunId });
      fetchAssets();
      fetchRuns();
      if (res.mode === 'run' && res.run_id === currentRunId) {
        setIsRunning(true); // polling jalan lagi sampai run kembali ke awaiting_approval
        await refreshRun(res.run_id);
      }
      setStatusMessage({
        type: 'success',
        text: res.mode === 'run'
          ? 'Membuat kandidat pose baru... run akan kembali ke "Menunggu Approval" setelah selesai (bisa 1–2 menit).'
          : 'Membuat kandidat pose baru di Asset Library. Muat ulang daftar aset beberapa saat lagi untuk meninjaunya.'
      });
    } catch (err) {
      setStatusMessage({ type: 'error', text: `Gagal membuat ulang pose: ${err.message}` });
    } finally {
      setRegeneratingId(null);
    }
  };

  // Resume Run Manual
  const handleResumeRun = async () => {
    if (!currentRunId) return;
    setResumingRun(true);
    try {
      await api.resumeRun(currentRunId);
      setIsRunning(true);
      setStatusMessage({ type: 'success', text: 'Pipeline dilanjutkan untuk merender slide final.' });
    } catch (err) {
      setStatusMessage({ type: 'error', text: `Gagal melanjutkan: ${err.message}` });
    } finally {
      setResumingRun(false);
    }
  };

  const handleSaveBrand = async (e) => {
    e.preventDefault();
    setBrandSaving(true);
    try {
      await api.updateBrand(brandForm);
      fetchBrand();
      setStatusMessage({ type: 'success', text: 'Konfigurasi brand, nomor telepon, dan warna khas berhasil disimpan!' });
    } catch (err) {
      setStatusMessage({ type: 'error', text: `Gagal menyimpan: ${err.message}` });
    } finally {
      setBrandSaving(false);
    }
  };

  // Upload Logo
  const handleLogoUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLogoUploading(true);
    try {
      await api.uploadLogo(file);
      fetchBrand();
      setStatusMessage({ type: 'success', text: 'Logo berhasil diupload ke assets/logo.png!' });
    } catch (err) {
      setStatusMessage({ type: 'error', text: `Gagal upload logo: ${err.message}` });
    } finally {
      setLogoUploading(false);
    }
  };

  // Upload Talent Raw Photo
  const handleTalentUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setTalentUploading(true);
    try {
      await api.uploadTalentReference(file, 'operator_01');
      fetchAssets();
      setStatusMessage({ type: 'success', text: 'Foto orang mentah tanpa pose berhasil diupload ke data/people/operator_01/reference.png! Cloudflare siap men-generate pose baru otomatis.' });
    } catch (err) {
      setStatusMessage({ type: 'error', text: `Gagal upload foto orang: ${err.message}` });
    } finally {
      setTalentUploading(false);
    }
  };

  const slides = runData?.design?.slides || [];
  const video = runData?.video || null;
  // Format run aktif: pakai data dari server kalau sudah ada, fallback ke pilihan form saat baru dipicu
  const isVideoRun = (runData?.format ?? formatType) === 'video';
  const runFailed = runData?.status === 'failed';
  const pendingItems = runData?.design?.pending_review || [];
  const pendingLeft = pendingItems.some(p => (p.status ? p.status === 'pending_review' : true));

  return (
    <div className="flex flex-col min-h-screen">
      {/* Header Bar */}
      <header className="border-b border-gray-800 bg-[#0d1322] px-6 py-4 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-50">
        <div className="flex items-center space-x-3">
          <div className="bg-emerald-500/10 p-2 rounded-lg border border-emerald-500/30 text-emerald-400">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-wide flex items-center gap-2">
              AUTO-CONTENT AGENT
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                GTNIC 2026
              </span>
            </h1>
            <p className="text-xs text-gray-400">Enterprise Social Media Orchestrator • Zero-AI-Slop</p>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center bg-gray-900 border border-gray-800 rounded-lg p-1 text-xs font-medium">
          <button
            onClick={() => setActiveTab('generator')}
            className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition ${
              activeTab === 'generator' ? 'bg-emerald-600 text-white font-semibold' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" /> Pipeline Generator
          </button>
          <button
            onClick={() => setActiveTab('brand_settings')}
            className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition ${
              activeTab === 'brand_settings' ? 'bg-emerald-600 text-white font-semibold' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Settings className="w-3.5 h-3.5" /> Brand & Asset Setup
          </button>
          <button
            onClick={() => setActiveTab('assets')}
            className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition ${
              activeTab === 'assets' ? 'bg-emerald-600 text-white font-semibold' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <ImageIcon className="w-3.5 h-3.5" /> Asset Library ({assetCounts.all ?? assets.length})
            {(assetCounts.pending_review || 0) > 0 && (
              <span className="ml-0.5 px-1.5 py-0.5 rounded-full bg-amber-500 text-black text-[10px] font-bold leading-none">
                {assetCounts.pending_review}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('runs')}
            className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition ${
              activeTab === 'runs' ? 'bg-emerald-600 text-white font-semibold' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <History className="w-3.5 h-3.5" /> Riwayat Run
            {pendingRunsCount > 0 && (
              <span className="ml-0.5 px-1.5 py-0.5 rounded-full bg-amber-500 text-black text-[10px] font-bold leading-none">
                {pendingRunsCount}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('layouts')}
            className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition ${
              activeTab === 'layouts' ? 'bg-emerald-600 text-white font-semibold' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Layers className="w-3.5 h-3.5" /> Layout Engines ({layouts.length})
          </button>
        </div>

        {/* Brand Badge */}
        {brand && (
          <div className="hidden md:flex items-center gap-2 text-xs bg-gray-900 border border-gray-800 px-3 py-1.5 rounded-full text-gray-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            Brand: <strong className="text-white">{brand.company || brand.name || 'Belum Diisi'}</strong>
          </div>
        )}
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-4 md:p-6 max-w-7xl w-full mx-auto">
        {statusMessage && (
          <div className={`mb-6 p-4 rounded-xl border flex items-center justify-between text-xs ${
            statusMessage.type === 'success' ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300' : 'bg-red-950/40 border-red-800 text-red-300'
          }`}>
            <span>{statusMessage.text}</span>
            <button onClick={() => setStatusMessage(null)} className="font-bold underline ml-4">Tutup</button>
          </div>
        )}

        {/* TAB 1: PIPELINE GENERATOR */}
        {activeTab === 'generator' && (
          <div className="space-y-6">
            {/* Input Form Panel */}
            <div className="bg-gray-900/80 border border-gray-800 rounded-xl p-5 shadow-lg backdrop-blur">
              <form onSubmit={handleGenerate} className="space-y-4">
                <div className="flex flex-col md:flex-row gap-4">
                  <div className="flex-1">
                    <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1.5">
                      Topik atau Kueri Konten Industri
                    </label>
                    <input
                      type="text"
                      value={topic}
                      onChange={(e) => setTopic(e.target.value)}
                      placeholder="Contoh: 5 Strategi Kelola Cashflow Usaha Menghadapi Inflasi 2026"
                      className="w-full bg-gray-950 border border-gray-750 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition"
                      disabled={isRunning}
                    />
                  </div>

                  <div className="w-full md:w-56">
                    <label className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1.5">
                      Format Konten
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setFormatType('carousel')}
                        className={`py-2 text-xs font-semibold rounded-lg border transition flex items-center justify-center gap-1.5 ${
                          formatType === 'carousel'
                            ? 'bg-emerald-600/20 border-emerald-500 text-emerald-300'
                            : 'bg-gray-950 border-gray-800 text-gray-400 hover:border-gray-700'
                        }`}
                      >
                        <Layers className="w-3.5 h-3.5" /> Carousel (IG)
                      </button>
                      <button
                        type="button"
                        onClick={() => setFormatType('video')}
                        className={`py-2 text-xs font-semibold rounded-lg border transition flex items-center justify-center gap-1.5 ${
                          formatType === 'video'
                            ? 'bg-indigo-600/20 border-indigo-500 text-indigo-300'
                            : 'bg-gray-950 border-gray-800 text-gray-400 hover:border-gray-700'
                        }`}
                      >
                        <Video className="w-3.5 h-3.5" /> Video Reels
                      </button>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-gray-800/60">
                  <div className="flex items-center gap-4 text-xs text-gray-400">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={freshResearch}
                        onChange={(e) => setFreshResearch(e.target.checked)}
                        className="rounded bg-gray-900 border-gray-700 text-emerald-600 focus:ring-emerald-500"
                      />
                      <span>Live Tavily Search ({formatType === 'video' ? 'Riset Fakta Topik Reels' : 'Riset Fakta Baru'})</span>
                    </label>

                    {formatType === 'video' && (
                      <div className="flex items-center gap-2 pl-2 border-l border-gray-800">
                        <span>Target Durasi:</span>
                        <select
                          value={targetDuration}
                          onChange={(e) => setTargetDuration(Number(e.target.value))}
                          className="bg-gray-950 border border-gray-800 text-gray-200 text-xs rounded px-2 py-1"
                        >
                          <option value={15}>15 Detik</option>
                          <option value={30}>30 Detik (Standar)</option>
                          <option value={60}>60 Detik</option>
                        </select>
                      </div>
                    )}
                  </div>

                  <button
                    type="submit"
                    disabled={isRunning}
                    className={`px-5 py-2.5 rounded-lg text-sm font-semibold flex items-center gap-2 shadow-lg transition ${
                      isRunning
                        ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                        : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-900/30'
                    }`}
                  >
                    {isRunning ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
                        Agen Sedang Bekerja...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4" />
                        Jalankan Autonomous Pipeline
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>

            {/* Split Grid: Live Preview (Kiri) vs Agent Reasoning & Tool Calls (Kanan) */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              
              {/* KOLOM KIRI: PREVIEW HASIL (Carousel / Video Player) */}
              <div className="lg:col-span-6 space-y-4">
                <div className="bg-gray-900/90 border border-gray-800 rounded-xl overflow-hidden shadow-xl flex flex-col">
                  {/* Card Header */}
                  <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between bg-gray-950">
                    <span className="text-xs font-semibold text-gray-300 flex items-center gap-1.5">
                      <Eye className="w-4 h-4 text-emerald-400" />
                      Preview Hasil Konten
                    </span>
                    {runData && (
                      <span className={`text-[11px] px-2 py-0.5 rounded font-mono uppercase ${
                        runData.status === 'ok' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' :
                        runData.status === 'running' ? 'bg-amber-950 text-amber-400 border border-amber-800 animate-pulse' :
                        'bg-red-950 text-red-400 border border-red-800'
                      }`}>
                        {runData.status}
                      </span>
                    )}
                  </div>

                  {/* Card Body Display */}
                  <div className="p-4 flex flex-col items-center justify-center min-h-[460px] bg-black/40">
                    {/* BANNER AWAITING APPROVAL: Tampilkan Pose yang menunggu persetujuan */}
                    {runData?.status === 'awaiting_approval' && (
                      <div className="w-full mb-4 p-4 bg-amber-950/40 border border-amber-600/60 rounded-xl space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                            <AlertCircle className="w-4 h-4 text-amber-400" />
                            Persetujuan Manusia Diperlukan (Human-in-the-Loop)
                          </span>
                          <span className="text-[10px] bg-amber-900/60 text-amber-200 px-2 py-0.5 rounded border border-amber-700 font-mono">
                            Awaiting Approval
                          </span>
                        </div>
                        <p className="text-xs text-gray-300 leading-relaxed">
                          Cloudflare Workers AI telah men-generate pose baru dari foto mentahan Anda. Tinjau potongan pose transparan di bawah ini sebelum poster dirakit final.
                        </p>

                        {/* List pose pending review */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                          {runData?.design?.pending_review?.map((pr) => (
                            <div key={pr.id} className="p-3 bg-gray-950 rounded-lg border border-gray-800 flex items-center gap-3">
                              <div className="w-14 h-14 bg-black rounded border border-gray-800 flex items-center justify-center overflow-hidden shrink-0">
                                {pr.url ? (
                                  <img src={pr.url} alt={pr.pose} className="w-full h-full object-contain" />
                                ) : (
                                  <ImageIcon className="w-6 h-6 text-gray-700" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0 space-y-1">
                                <div className="flex items-center justify-between">
                                  <span className="text-xs font-semibold text-white truncate">Pose: #{pr.pose}</span>
                                  <span className={`text-[9px] px-1.5 py-0.2 rounded font-mono ${pr.qc?.ok ? 'bg-emerald-950 text-emerald-400' : 'bg-red-950 text-red-400'}`}>
                                    {pr.qc?.ok ? 'QC OK' : 'QC GAGAL'}
                                  </span>
                                </div>
                                {pr.status && pr.status !== 'pending_review' ? (
                                  <div className="flex items-center gap-2 pt-1">
                                    <span className={`inline-block text-[10px] px-2 py-0.5 rounded font-mono ${
                                      pr.status === 'approved' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                                        : 'bg-red-950 text-red-400 border border-red-800'
                                    }`}>
                                      {pr.status === 'approved' ? 'Disetujui' : pr.status === 'rejected' ? 'Ditolak' : pr.status}
                                    </span>
                                    {pr.status === 'rejected' && (
                                      <button
                                        onClick={() => handleRegenerate(pr.id, runData?.run_id)}
                                        disabled={regeneratingId === pr.id || resumingRun}
                                        className="px-2.5 py-1 bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white text-[11px] font-semibold rounded flex items-center gap-1 transition"
                                      >
                                        <RefreshCw className={`w-3 h-3 ${regeneratingId === pr.id ? 'animate-spin' : ''}`} /> Buat Ulang
                                      </button>
                                    )}
                                  </div>
                                ) : (
                                <div className="flex gap-2 pt-1">
                                  <button
                                    onClick={() => handleApproveAsset(pr.id, 'approved')}
                                    disabled={approvingAssetId === pr.id || resumingRun}
                                    className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-[11px] font-semibold rounded flex items-center gap-1 transition"
                                  >
                                    <Check className="w-3 h-3" /> Setujui
                                  </button>
                                  <button
                                    onClick={() => handleApproveAsset(pr.id, 'rejected')}
                                    disabled={approvingAssetId === pr.id || resumingRun}
                                    className="px-2.5 py-1 bg-gray-800 hover:bg-red-900/60 text-gray-300 hover:text-red-300 text-[11px] font-semibold rounded transition"
                                  >
                                    Tolak
                                  </button>
                                </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>

                        <div className="pt-2 flex justify-end">
                          <button
                            onClick={handleResumeRun}
                            disabled={resumingRun || pendingLeft}
                            title={pendingLeft ? 'Putuskan semua pose terlebih dahulu' : undefined}
                            className="px-4 py-1.5 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded text-xs font-semibold flex items-center gap-1.5 transition shadow"
                          >
                            {resumingRun ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                            Lanjutkan Pipeline (Resume)
                          </button>
                        </div>
                      </div>
                    )}

                    {/* BANNER AWAITING ASSETS: pose belum tersedia (mis. regenerate gagal) */}
                    {runData?.status === 'awaiting_assets' && (
                      <div className="w-full mb-4 p-4 bg-orange-950/30 border border-orange-700/60 rounded-xl space-y-2">
                        <span className="text-xs font-bold text-orange-300 flex items-center gap-1.5">
                          <AlertCircle className="w-4 h-4" />
                          Pose belum tersedia
                        </span>
                        <p className="text-xs text-gray-300">
                          Slide dirender tanpa foto untuk pose: <strong>{(runData.design?.missing_poses || []).join(', ') || '-'}</strong>.
                          {' '}Lanjutkan pipeline untuk mencoba membuat pose baru.
                        </p>
                        {runData.error && (
                          <p className="text-[11px] text-orange-200/80 break-words">{runData.error}</p>
                        )}
                        <div className="flex justify-end">
                          <button
                            onClick={handleResumeRun}
                            disabled={resumingRun}
                            className="px-4 py-1.5 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white rounded text-xs font-semibold flex items-center gap-1.5 transition"
                          >
                            {resumingRun ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                            Lanjutkan Pipeline (Resume)
                          </button>
                        </div>
                      </div>
                    )}

                    {video?.url ? (
                      <div className="w-full max-w-[300px] flex flex-col items-center space-y-3">
                        {/* Video Reels (9:16 / 1080x1920) */}
                        <div className="relative w-full aspect-[9/16] bg-gray-950 rounded-lg overflow-hidden border border-gray-800 shadow-2xl">
                          <video
                            key={video.url}
                            src={video.url}
                            controls
                            playsInline
                            loop
                            preload="metadata"
                            className="w-full h-full object-contain bg-black"
                          />
                        </div>
                        <div className="flex items-center justify-between w-full text-[11px] text-gray-400 font-mono">
                          <span className="flex items-center gap-1.5">
                            <Film className="w-3.5 h-3.5 text-indigo-400" />
                            {video.scenes_count} scene • {Number(video.duration_sec).toFixed(1)}s • {Number(video.file_size_mb).toFixed(2)} MB
                          </span>
                          <a
                            href={video.url}
                            download
                            className="flex items-center gap-1 text-indigo-300 hover:text-indigo-200 underline"
                          >
                            <Download className="w-3.5 h-3.5" /> Unduh MP4
                          </a>
                        </div>
                        {video.issues?.length > 0 && (
                          <ul className="w-full text-[10.5px] text-amber-300 bg-amber-950/30 border border-amber-800/50 rounded p-2 list-disc list-inside space-y-0.5">
                            {video.issues.map((issue, i) => <li key={i}>{issue}</li>)}
                          </ul>
                        )}
                      </div>
                    ) : slides.length > 0 ? (
                      <div className="w-full max-w-[340px] flex flex-col items-center space-y-3">
                        {/* Slide Display (Aspect 4:5 1080x1350) */}
                        <div className="relative w-full aspect-[4/5] bg-gray-950 rounded-lg overflow-hidden border border-gray-800 shadow-2xl">
                          <img
                            src={slides[currentSlideIndex]?.image_url}
                            alt={`Slide ${currentSlideIndex + 1}`}
                            className="w-full h-full object-contain"
                          />
                          <div className="absolute top-2 right-2 bg-black/75 px-2 py-0.5 rounded text-[10px] font-mono text-white backdrop-blur">
                            {currentSlideIndex + 1} / {slides.length}
                          </div>
                        </div>

                        {/* Slide Carousel Controls */}
                        <div className="flex items-center justify-between w-full pt-1">
                          <button
                            onClick={() => setCurrentSlideIndex(prev => Math.max(0, prev - 1))}
                            disabled={currentSlideIndex === 0}
                            className="p-1.5 rounded-md bg-gray-800 hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition text-gray-300"
                          >
                            <ChevronLeft className="w-4 h-4" />
                          </button>
                          <span className="text-xs text-gray-400 font-mono">
                            Slide {currentSlideIndex + 1} of {slides.length}
                          </span>
                          <button
                            onClick={() => setCurrentSlideIndex(prev => Math.min(slides.length - 1, prev + 1))}
                            disabled={currentSlideIndex === slides.length - 1}
                            className="p-1.5 rounded-md bg-gray-800 hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition text-gray-300"
                          >
                            <ChevronRight className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    ) : runFailed ? (
                      <div className="w-full max-w-sm flex flex-col items-center text-center p-6 space-y-3 bg-red-950/20 border border-red-800/50 rounded-xl">
                        <AlertCircle className="w-8 h-8 text-red-400" />
                        <p className="text-sm text-red-300 font-semibold">
                          {isVideoRun ? 'Pembuatan video gagal' : 'Pembuatan konten gagal'}
                        </p>
                        <p className="text-xs text-red-200/80 break-words max-w-xs">
                          {runData.error || video?.issues?.join('; ') || 'Terjadi kesalahan. Lihat log agen di sebelah kanan untuk detailnya.'}
                        </p>
                      </div>
                    ) : isRunning ? (
                      <div className="flex flex-col items-center justify-center text-center p-8 space-y-3">
                        <RefreshCw className={`w-8 h-8 animate-spin ${isVideoRun ? 'text-indigo-400' : 'text-emerald-400'}`} />
                        <p className="text-sm text-gray-300 font-medium">
                          {isVideoRun
                            ? 'Agen sedang menulis naskah, voiceover, dan merakit video...'
                            : 'Agen sedang meriset & merender visual...'}
                        </p>
                        <p className="text-xs text-gray-500 max-w-xs">Perhatikan jendela "Agent Reasoning" di sebelah kanan untuk melihat proses berpikir agen.</p>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center text-center p-8 space-y-2 text-gray-500">
                        <Layers className="w-10 h-10 opacity-30" />
                        <p className="text-sm">Belum ada konten yang dibuat.</p>
                        <p className="text-xs max-w-xs">Ketik topik di atas lalu klik "Jalankan Autonomous Pipeline" untuk memulai.</p>
                      </div>
                    )}
                  </div>

                  {/* Info biaya & status publish untuk run video */}
                  {isVideoRun && runData && (
                    <div className="p-4 border-t border-gray-800 bg-gray-950/80 space-y-3">
                      {publishResult && (
                        <div className={`p-3 rounded-lg text-xs border ${
                          publishResult.status === 'published' ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300' : 'bg-red-950/40 border-red-800 text-red-300'
                        }`}>
                          <div className="font-semibold flex items-center gap-1.5">
                            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                            {publishResult.status === 'published' ? 'Reels Berhasil di-Publish ke Instagram!' : 'Gagal Publikasi Reels'}
                          </div>
                          {publishResult.permalink && (
                            <a 
                              href={publishResult.permalink} 
                              target="_blank" 
                              rel="noreferrer" 
                              className="text-emerald-400 underline block mt-1 hover:text-emerald-300"
                            >
                              Lihat Reels di Instagram &rarr;
                            </a>
                          )}
                          {publishResult.error && (
                            <p className="text-red-400 mt-1">{publishResult.error}</p>
                          )}
                        </div>
                      )}

                      <div className="flex items-center justify-between gap-3">
                        <div className="text-[11px] text-gray-400 flex items-center gap-2">
                          <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
                          Biaya: <strong className="text-emerald-400 font-mono">${(runData.cost_usd ?? 0).toFixed(4)}</strong>
                          <span className="text-gray-600">|</span>
                          Token: <span className="font-mono text-gray-300">{(runData.tokens_in ?? 0) + (runData.tokens_out ?? 0)}</span>
                        </div>
                        <button
                          onClick={handlePublish}
                          disabled={publishing || runData.status !== 'ok'}
                          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-800 disabled:text-gray-600 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition shadow"
                        >
                          {publishing ? (
                            <>
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Mengunggah Reels...
                            </>
                          ) : (
                            <>
                              <Send className="w-3.5 h-3.5" /> Publish Reels to Instagram
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Caption & Publish Action Bar untuk Carousel */}
                  {!isVideoRun && runData?.plan && (
                    <div className="p-4 border-t border-gray-800 bg-gray-950/80 space-y-3">
                      <div>
                        <span className="text-xs font-semibold text-gray-400 block mb-1">Draf Caption Instagram:</span>
                        <div className="text-xs text-gray-300 bg-gray-900 p-2.5 rounded border border-gray-800 max-h-24 overflow-y-auto leading-relaxed">
                          {runData.plan.caption || 'Tidak ada caption.'}
                        </div>
                      </div>

                      {publishResult && (
                        <div className={`p-3 rounded-lg text-xs border ${
                          publishResult.status === 'published' ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300' : 'bg-red-950/40 border-red-800 text-red-300'
                        }`}>
                          <div className="font-semibold flex items-center gap-1.5">
                            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                            {publishResult.status === 'published' ? 'Berhasil dikirim ke Instagram!' : 'Gagal Publikasi'}
                          </div>
                          {publishResult.permalink && (
                            <a 
                              href={publishResult.permalink} 
                              target="_blank" 
                              rel="noreferrer" 
                              className="text-emerald-400 underline block mt-1 hover:text-emerald-300"
                            >
                              Lihat Postingan di Instagram &rarr;
                            </a>
                          )}
                          {publishResult.error && (
                            <p className="text-red-400 mt-1">{publishResult.error}</p>
                          )}
                        </div>
                      )}

                      <div className="flex items-center justify-between pt-1">
                        <div className="text-[11px] text-gray-400 flex items-center gap-2">
                          <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
                          Biaya: <strong className="text-emerald-400 font-mono">${runData.cost_usd.toFixed(4)}</strong>
                          <span className="text-gray-600">|</span>
                          Token: <span className="font-mono text-gray-300">{runData.tokens_in + runData.tokens_out}</span>
                        </div>

                        <button
                          onClick={handlePublish}
                          disabled={publishing || runData.status !== 'ok'}
                          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-800 disabled:text-gray-600 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition shadow"
                        >
                          {publishing ? (
                            <>
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Menerbitkan...
                            </>
                          ) : (
                            <>
                              <Send className="w-3.5 h-3.5" /> Publish to Instagram
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* KOLOM KANAN: AGENT REASONING & TOOL CALLS OBSERVABILITY LOG */}
              <div className="lg:col-span-6 space-y-4">
                <div className="bg-gray-900/90 border border-gray-800 rounded-xl overflow-hidden shadow-xl flex flex-col h-full min-h-[560px]">
                  {/* Header Log */}
                  <div className="px-4 py-3 border-b border-gray-800 bg-gray-950 flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-300 flex items-center gap-1.5">
                      <Terminal className="w-4 h-4 text-amber-400" />
                      Agent Thought Process & Tool Calls (Real-Time)
                    </span>
                    <span className="text-[11px] text-gray-500 font-mono">
                      {events.length} Events Logged
                    </span>
                  </div>

                  {/* Terminal Log Body */}
                  <div className="flex-1 p-4 bg-[#080c14] overflow-y-auto font-mono text-[11px] space-y-2.5 max-h-[500px]">
                    {events.length === 0 ? (
                      <div className="h-full flex items-center justify-center text-gray-600 italic">
                        Menunggu instruksi pipeline...
                      </div>
                    ) : (
                      events.map((e, idx) => {
                        const isTool = e.kind === 'tool';
                        const isLLM = e.kind === 'llm';
                        const isGuard = e.kind === 'guardrail';
                        const isErr = e.kind === 'error';

                        return (
                          <div 
                            key={e.id || idx}
                            className={`p-2 rounded border transition ${
                              isErr ? 'bg-red-950/30 border-red-800/60 text-red-300' :
                              isGuard ? 'bg-purple-950/20 border-purple-800/50 text-purple-300' :
                              isTool ? 'bg-blue-950/20 border-blue-800/50 text-blue-300' :
                              isLLM ? 'bg-emerald-950/20 border-emerald-800/50 text-emerald-300' :
                              'bg-gray-900/40 border-gray-800 text-gray-300'
                            }`}
                          >
                            <div className="flex items-center justify-between text-[10px] text-gray-400 mb-1">
                              <div className="flex items-center gap-1.5">
                                <span className="text-amber-400">[{e.step || 'pipeline'}]</span>
                                <span className="uppercase font-bold text-gray-300">{e.kind}: {e.name}</span>
                              </div>
                              <span className="text-gray-500">{e.timestamp?.slice(11, 19)}</span>
                            </div>

                            {/* Detail Message / Tool Payload */}
                            {e.detail && (
                              <div className="text-gray-300 text-[10.5px] leading-relaxed break-words">
                                {typeof e.detail === 'object' ? JSON.stringify(e.detail) : e.detail}
                              </div>
                            )}

                            {/* Latency / Cost metadata */}
                            {(e.cost_usd > 0 || e.duration_ms > 0) && (
                              <div className="mt-1 pt-1 border-t border-gray-800/40 text-[9.5px] text-gray-500 flex gap-3">
                                {e.duration_ms > 0 && <span>Duration: {(e.duration_ms / 1000).toFixed(2)}s</span>}
                                {e.cost_usd > 0 && <span>Cost: ${e.cost_usd.toFixed(4)}</span>}
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                    <div ref={logEndRef} />
                  </div>

                  {/* Footer Log Info */}
                  <div className="p-2.5 bg-gray-950 border-t border-gray-800 text-[10px] text-gray-500 flex items-center justify-between">
                    <span>Multi-Agent Engine: Llama-3-70B • Tavily • Playwright</span>
                    <span>100% Traceable Audit Log</span>
                  </div>
                </div>
              </div>

            </div>
          </div>
        )}

        {/* TAB 2: BRAND & ASSET SETUP (BARU: Input Logo, No Telp, Warna, Foto Mentah) */}
        {activeTab === 'brand_settings' && (
          <div className="space-y-6">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <h2 className="text-base font-bold text-white flex items-center gap-2 mb-1">
                <Settings className="w-4 h-4 text-emerald-400" />
                Setup Brand, Identitas, & Input Aset Mentah
              </h2>
              <p className="text-xs text-gray-400">
                Atur identitas korporat, kontak (nomor telepon & Instagram), palet warna khas, upload logo, serta mentahan foto orang tanpa pose untuk Cloudflare Workers AI.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Form Konfigurasi Brand & Kontak */}
              <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-5 space-y-4">
                <h3 className="text-sm font-bold text-white flex items-center gap-2 border-b border-gray-800 pb-3">
                  <Phone className="w-4 h-4 text-emerald-400" />
                  Profil Usaha & Nomor Kontak
                </h3>
                <form onSubmit={handleSaveBrand} className="space-y-3 text-xs">
                  <div>
                    <label className="block text-gray-300 mb-1 font-semibold">Nama Perusahaan / Brand:</label>
                    <input
                      type="text"
                      value={brandForm.company}
                      onChange={e => setBrandForm({...brandForm, company: e.target.value})}
                      placeholder="Contoh: PT Manufaktur Komponen Indonesia"
                      className="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-white"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-gray-300 mb-1 font-semibold">Nomor Telepon / WA:</label>
                      <input
                        type="text"
                        value={brandForm.phone}
                        onChange={e => setBrandForm({...brandForm, phone: e.target.value})}
                        placeholder="Contoh: 0812-3456-7890"
                        className="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-white font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-300 mb-1 font-semibold">Handle Instagram:</label>
                      <input
                        type="text"
                        value={brandForm.handle}
                        onChange={e => setBrandForm({...brandForm, handle: e.target.value})}
                        placeholder="Contoh: @perusahaanku"
                        className="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-white font-mono"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-gray-300 mb-1 font-semibold">Sektor Industri:</label>
                    <input
                      type="text"
                      value={brandForm.industry}
                      onChange={e => setBrandForm({...brandForm, industry: e.target.value})}
                      placeholder="Contoh: Manufaktur Komponen Mesin Presisi"
                      className="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-gray-300 mb-1 font-semibold">Deskripsi Singkat Usaha:</label>
                    <textarea
                      value={brandForm.description}
                      onChange={e => setBrandForm({...brandForm, description: e.target.value})}
                      placeholder="Deskripsi singkat untuk konteks agen AI saat meriset konten..."
                      rows={2}
                      className="w-full bg-gray-950 border border-gray-800 rounded px-3 py-2 text-white resize-none"
                    />
                  </div>

                  {/* Warna Khas */}
                  <div className="pt-2 border-t border-gray-800">
                    <label className="block text-gray-300 mb-2 font-semibold flex items-center gap-1.5">
                      <Palette className="w-3.5 h-3.5 text-emerald-400" />
                      Warna Khas Desain (Hex Color)
                    </label>
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <span className="text-[10px] text-gray-400 block mb-1">Primary (Background)</span>
                        <div className="flex items-center gap-2">
                          <input
                            type="color"
                            value={brandForm.primary_color}
                            onChange={e => setBrandForm({...brandForm, primary_color: e.target.value})}
                            className="w-7 h-7 rounded border-0 cursor-pointer bg-transparent"
                          />
                          <input
                            type="text"
                            value={brandForm.primary_color}
                            onChange={e => setBrandForm({...brandForm, primary_color: e.target.value})}
                            className="w-full bg-gray-950 border border-gray-800 rounded px-2 py-1 text-[11px] font-mono text-white"
                          />
                        </div>
                      </div>
                      <div>
                        <span className="text-[10px] text-gray-400 block mb-1">Secondary (Light)</span>
                        <div className="flex items-center gap-2">
                          <input
                            type="color"
                            value={brandForm.secondary_color}
                            onChange={e => setBrandForm({...brandForm, secondary_color: e.target.value})}
                            className="w-7 h-7 rounded border-0 cursor-pointer bg-transparent"
                          />
                          <input
                            type="text"
                            value={brandForm.secondary_color}
                            onChange={e => setBrandForm({...brandForm, secondary_color: e.target.value})}
                            className="w-full bg-gray-950 border border-gray-800 rounded px-2 py-1 text-[11px] font-mono text-white"
                          />
                        </div>
                      </div>
                      <div>
                        <span className="text-[10px] text-gray-400 block mb-1">Accent (Highlight)</span>
                        <div className="flex items-center gap-2">
                          <input
                            type="color"
                            value={brandForm.accent_color}
                            onChange={e => setBrandForm({...brandForm, accent_color: e.target.value})}
                            className="w-7 h-7 rounded border-0 cursor-pointer bg-transparent"
                          />
                          <input
                            type="text"
                            value={brandForm.accent_color}
                            onChange={e => setBrandForm({...brandForm, accent_color: e.target.value})}
                            className="w-full bg-gray-950 border border-gray-800 rounded px-2 py-1 text-[11px] font-mono text-white"
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="pt-2">
                    <button
                      type="submit"
                      disabled={brandSaving}
                      className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-semibold flex items-center justify-center gap-1.5 transition"
                    >
                      {brandSaving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                      Simpan Konfigurasi Brand
                    </button>
                  </div>
                </form>
              </div>

              {/* Upload Logo & Foto Mentahan Orang */}
              <div className="space-y-6">
                {/* Upload Logo */}
                <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-5 space-y-3">
                  <div className="flex items-center justify-between border-b border-gray-800 pb-3">
                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                      <Upload className="w-4 h-4 text-emerald-400" />
                      Logo Brand
                    </h3>
                    {brand?.has_logo && (
                      <span className="text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 px-2 py-0.5 rounded flex items-center gap-1 font-semibold">
                        <Check className="w-3 h-3" /> Terpasang
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400">
                    Upload file logo (PNG dengan background transparan disarankan). Logo akan otomatis terpasang pada header setiap slide poster carousel.
                  </p>

                  {brand?.has_logo && brand?.logo_url && (
                    <div className="p-3 bg-gray-950 rounded-lg border border-gray-800 flex items-center gap-3">
                      <div className="w-12 h-12 bg-black/60 rounded border border-gray-800 flex items-center justify-center p-1 overflow-hidden">
                        <img src={brand.logo_url} alt="Logo Brand" className="w-full h-full object-contain" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <span className="text-xs font-semibold text-gray-200 block truncate">Logo Aktif (assets/logo.png)</span>
                        <span className="text-[10px] text-emerald-400">Siap dipakai di header poster</span>
                      </div>
                    </div>
                  )}

                  <label className="block border-2 border-dashed border-gray-800 hover:border-emerald-500/50 rounded-lg p-4 text-center cursor-pointer transition bg-gray-950/50">
                    <input
                      type="file"
                      accept="image/png, image/jpeg"
                      onChange={handleLogoUpload}
                      disabled={logoUploading}
                      className="hidden"
                    />
                    <Upload className="w-6 h-6 text-gray-500 mx-auto mb-1.5" />
                    <span className="text-xs text-gray-300 font-medium block">
                      {logoUploading ? 'Mengupload logo...' : brand?.has_logo ? 'Ganti File Logo (PNG/JPEG)' : 'Klik untuk Pilih File Logo (PNG/JPEG)'}
                    </span>
                    <span className="text-[10px] text-gray-500">Disimpan ke assets/logo.png</span>
                  </label>
                </div>

                {/* Upload Mentahan Foto Orang (Tanpa Pose) */}
                <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-5 space-y-3">
                  <div className="flex items-center justify-between border-b border-gray-800 pb-3">
                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                      <UserCheck className="w-4 h-4 text-emerald-400" />
                      Mentahan Foto Orang (Tanpa Pose)
                    </h3>
                    {brand?.has_talent_ref && (
                      <span className="text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 px-2 py-0.5 rounded flex items-center gap-1 font-semibold">
                        <Check className="w-3 h-3" /> Terpasang
                      </span>
                    )}
                  </div>
                  <div className="bg-emerald-950/20 border border-emerald-800/40 p-3 rounded-lg text-[11px] text-emerald-300 leading-relaxed">
                    <strong>Alur Cloudflare Otomatis:</strong> Unggah 1 foto wajah / setengah badan orang mentahan tanpa pose. Saat pipeline berjalan dan layout membutuhkan pose tertentu (senyum, mikir, menunjuk), Cloudflare Workers AI (<code className="font-mono text-emerald-200">FLUX-2 Klein</code>) akan otomatis men-generate orang tersebut ke pose yang dibutuhkan dan menghapus background-nya secara instan!
                  </div>

                  {brand?.has_talent_ref && brand?.talent_ref_url && (
                    <div className="p-3 bg-gray-950 rounded-lg border border-gray-800 flex items-center gap-3">
                      <div className="w-12 h-12 bg-black/60 rounded border border-gray-800 flex items-center justify-center p-1 overflow-hidden">
                        <img src={brand.talent_ref_url} alt="Talent Referensi" className="w-full h-full object-cover" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <span className="text-xs font-semibold text-gray-200 block truncate">Foto Orang Aktif (operator_01)</span>
                        <span className="text-[10px] text-emerald-400">Siap digunakan untuk generate pose otomatis oleh Cloudflare</span>
                      </div>
                    </div>
                  )}

                  <label className="block border-2 border-dashed border-gray-800 hover:border-emerald-500/50 rounded-lg p-4 text-center cursor-pointer transition bg-gray-950/50">
                    <input
                      type="file"
                      accept="image/png, image/jpeg"
                      onChange={handleTalentUpload}
                      disabled={talentUploading}
                      className="hidden"
                    />
                    <UserCheck className="w-6 h-6 text-emerald-400 mx-auto mb-1.5" />
                    <span className="text-xs text-gray-300 font-medium block">
                      {talentUploading ? 'Mengupload foto mentah...' : brand?.has_talent_ref ? 'Ganti Foto Mentahan Orang (Tanpa Pose)' : 'Pilih Foto Mentahan Orang (Tanpa Pose)'}
                    </span>
                    <span className="text-[10px] text-gray-500">Disimpan ke data/people/operator_01/reference.png</span>
                  </label>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: ASSET LIBRARY */}
        {activeTab === 'assets' && (
          <div className="space-y-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <h2 className="text-base font-bold text-white flex items-center gap-2 mb-1">
                <ImageIcon className="w-4 h-4 text-emerald-400" />
                Enterprise Asset Library & Verified Talent Photos
              </h2>
              <p className="text-xs text-gray-400">
                Pustaka aset model/figur korporat dengan persetujuan lisensi (consent-check) dan proteksi anti-placeholder. Aset lama telah diarsipkan dengan aman.
              </p>
            </div>

            {/* Filter status aset */}
            <div className="flex flex-wrap items-center gap-2">
              {ASSET_FILTERS.map(f => (
                <button
                  key={f.key}
                  onClick={() => changeAssetFilter(f.key)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition flex items-center gap-1.5 ${
                    assetFilter === f.key
                      ? 'bg-emerald-600/20 border-emerald-500 text-emerald-300'
                      : 'bg-gray-950 border-gray-800 text-gray-400 hover:border-gray-700'
                  }`}
                >
                  {f.label}
                  <span className={`px-1.5 rounded-full text-[10px] font-mono ${
                    f.key === 'pending_review' && (assetCounts.pending_review || 0) > 0
                      ? 'bg-amber-500 text-black font-bold' : 'bg-gray-800 text-gray-300'
                  }`}>
                    {assetCounts[f.key] ?? 0}
                  </span>
                </button>
              ))}
            </div>

            {assets.length === 0 ? (
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center text-gray-500">
                <ImageIcon className="w-10 h-10 opacity-30 mx-auto mb-2" />
                <p className="text-sm">
                  {assetFilter === 'pending_review'
                    ? 'Tidak ada aset yang menunggu review.'
                    : 'Tidak ada aset pada filter ini.'}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  Buka tab <strong>Brand & Asset Setup</strong> untuk mengupload foto orang mentahan referensi.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
                {assets.map((asset) => (
                  <div key={asset.id} className="bg-gray-900 border border-gray-800 rounded-lg p-3 flex flex-col space-y-2">
                    <div className="aspect-square bg-black/60 rounded border border-gray-800 flex items-center justify-center overflow-hidden">
                      {asset.url ? (
                        <img src={asset.url} alt={asset.description} className="w-full h-full object-cover" />
                      ) : (
                        <ImageIcon className="w-8 h-8 text-gray-700" />
                      )}
                    </div>
                    <div>
                      <span className={`text-[10px] font-semibold uppercase tracking-wider block ${
                        asset.status === 'pending_review' ? 'text-amber-400'
                          : asset.status === 'rejected' ? 'text-red-400' : 'text-emerald-400'
                      }`}>
                        {asset.status === 'pending_review' ? 'menunggu review' : asset.status}
                      </span>
                      <p className="text-xs text-gray-200 font-medium truncate">{asset.description || 'Asset ' + asset.id}</p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {asset.tags?.map((tag, i) => (
                          <span key={i} className="text-[9px] bg-gray-800 text-gray-300 px-1.5 py-0.5 rounded">
                            #{tag}
                          </span>
                        ))}
                      </div>
                    </div>
                    {asset.status === 'pending_review' && (
                      <div className="flex gap-1.5 pt-1">
                        <button
                          onClick={() => handleApproveAsset(asset.id, 'approved', asset.run_id)}
                          disabled={approvingAssetId === asset.id}
                          className="flex-1 px-2 py-1 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-[11px] font-semibold rounded flex items-center justify-center gap-1 transition"
                        >
                          <Check className="w-3 h-3" /> Setujui
                        </button>
                        <button
                          onClick={() => handleApproveAsset(asset.id, 'rejected', asset.run_id)}
                          disabled={approvingAssetId === asset.id}
                          className="flex-1 px-2 py-1 bg-gray-800 hover:bg-red-900/60 text-gray-300 hover:text-red-300 disabled:opacity-50 text-[11px] font-semibold rounded transition"
                        >
                          Tolak
                        </button>
                      </div>
                    )}
                    {asset.status === 'rejected' && asset.person_id && (
                      <button
                        onClick={() => handleRegenerate(asset.id, asset.run_id)}
                        disabled={regeneratingId === asset.id}
                        className="px-2 py-1 bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 text-white text-[11px] font-semibold rounded flex items-center justify-center gap-1 transition"
                      >
                        <RefreshCw className={`w-3 h-3 ${regeneratingId === asset.id ? 'animate-spin' : ''}`} /> Buat Ulang Pose
                      </button>
                    )}
                    {asset.run_id && (
                      <button
                        onClick={() => openRun(asset.run_id)}
                        className="text-[10px] text-indigo-300 hover:text-indigo-200 underline text-left"
                      >
                        Buka run terkait
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB: RIWAYAT RUN */}
        {activeTab === 'runs' && (
          <div className="space-y-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <h2 className="text-base font-bold text-white flex items-center gap-2 mb-1">
                <History className="w-4 h-4 text-emerald-400" />
                Riwayat Run
              </h2>
              <p className="text-xs text-gray-400">
                Semua run terbaru. Klik sebuah run untuk membuka preview, log, dan melanjutkan yang menunggu persetujuan.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {[
                { key: 'all', label: 'Semua' },
                { key: 'awaiting_approval', label: 'Menunggu Approval' }
              ].map(f => (
                <button
                  key={f.key}
                  onClick={() => setRunsFilter(f.key)}
                  className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition flex items-center gap-1.5 ${
                    runsFilter === f.key
                      ? 'bg-emerald-600/20 border-emerald-500 text-emerald-300'
                      : 'bg-gray-950 border-gray-800 text-gray-400 hover:border-gray-700'
                  }`}
                >
                  {f.label}
                  {f.key === 'awaiting_approval' && pendingRunsCount > 0 && (
                    <span className="px-1.5 rounded-full text-[10px] font-mono bg-amber-500 text-black font-bold">
                      {pendingRunsCount}
                    </span>
                  )}
                </button>
              ))}
              <button
                onClick={fetchRuns}
                className="ml-auto p-1.5 rounded-md bg-gray-800 hover:bg-gray-700 text-gray-300 transition"
                title="Muat ulang"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>

            {runs.length === 0 ? (
              <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center text-gray-500">
                <Clock className="w-10 h-10 opacity-30 mx-auto mb-2" />
                <p className="text-sm">
                  {runsFilter === 'awaiting_approval' ? 'Tidak ada run yang menunggu approval.' : 'Belum ada run.'}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {runs.map(r => (
                  <button
                    key={r.run_id}
                    onClick={() => openRun(r.run_id, r.format, r.status)}
                    className={`text-left bg-gray-900 border rounded-lg p-3 flex gap-3 hover:border-emerald-600/60 transition ${
                      r.run_id === currentRunId ? 'border-emerald-700' : 'border-gray-800'
                    }`}
                  >
                    <div className="w-14 h-[70px] shrink-0 bg-black/60 rounded border border-gray-800 overflow-hidden flex items-center justify-center">
                      {r.thumbnail_url ? (
                        <img src={r.thumbnail_url} alt="" className="w-full h-full object-cover" />
                      ) : r.format === 'video' ? (
                        <Film className="w-5 h-5 text-indigo-400/70" />
                      ) : (
                        <Layers className="w-5 h-5 text-gray-700" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0 space-y-1">
                      <p className="text-xs font-semibold text-white truncate">{r.topic}</p>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded border font-mono uppercase ${RUN_STATUS_STYLE[r.status] || 'bg-gray-900 text-gray-400 border-gray-700'}`}>
                          {r.status}
                        </span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-800 text-gray-300 flex items-center gap-1">
                          {r.format === 'video' ? <Film className="w-3 h-3" /> : <Layers className="w-3 h-3" />}
                          {r.format === 'video' ? 'Reels' : 'Carousel'}
                        </span>
                        {r.pending_review_count > 0 && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500 text-black font-bold">
                            {r.pending_review_count} pose menunggu
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] text-gray-500 font-mono">
                        {fmtTime(r.started_at)} • ${Number(r.cost_usd || 0).toFixed(4)}
                      </p>
                      {r.status === 'failed' && r.error && (
                        <p className="text-[10px] text-red-400 truncate">{r.error}</p>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 4: LAYOUT CATALOG */}
        {activeTab === 'layouts' && (
          <div className="space-y-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <h2 className="text-base font-bold text-white flex items-center gap-2 mb-1">
                <Layers className="w-4 h-4 text-emerald-400" />
                Deterministic Layout Engine Registry
              </h2>
              <p className="text-xs text-gray-400">
                Katalog 30 template layout editorial (Cover, Penjelasan, Data, Perbandingan, dan CTA) — Seluruh 30 template telah berstatus <strong>APPROVED</strong> dan siap dipakai oleh Planner Agent.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {layouts.map((l, idx) => (
                <div key={idx} className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-white">{l.name || l.id}</span>
                    <span className="text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 px-2 py-0.5 rounded uppercase">
                      {l.role}
                    </span>
                  </div>
                  <p className="text-xs text-gray-400">{l.description || 'Layout template teruji'}</p>
                  <div className="text-[10px] text-gray-500 font-mono">
                    Status: <strong className="text-emerald-400">{l.status || 'approved'}</strong>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800 bg-[#0d1322] py-4 px-6 text-center text-xs text-gray-500">
        GTNIC 2026 Innovation Proposal Prototype • AI Agents for Enterprise Productivity
      </footer>
    </div>
  );
}