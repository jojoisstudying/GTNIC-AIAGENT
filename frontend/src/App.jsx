import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { PAGE_META } from './lib/nav';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import ToastStack from './components/ToastStack';
import Dashboard from './pages/Dashboard';
import Generator from './pages/Generator';
import Runs from './pages/Runs';
import Assets from './pages/Assets';
import Strategy from './pages/Strategy';
import Analytics from './pages/Analytics';
import Social from './pages/Social';
import BrandSetup from './pages/BrandSetup';
import Enterprise from './pages/Enterprise';
import Layouts from './pages/Layouts';
import Settings from './pages/Settings';

const LAST_RUN_KEY = 'agent-sosmed:last-run-id';
const POLL_INTERVAL_MS = 1500;
const TERMINAL_STATUSES = ['ok', 'failed', 'awaiting_approval', 'awaiting_assets'];

const readLastRunId = () => {
  try { return localStorage.getItem(LAST_RUN_KEY); } catch { return null; }
};
const saveLastRunId = (id) => {
  try { localStorage.setItem(LAST_RUN_KEY, id); } catch { /* storage diblokir: abaikan */ }
};
const forgetLastRunId = () => {
  try { localStorage.removeItem(LAST_RUN_KEY); } catch { /* abaikan */ }
};

let toastSeq = 0;

export default function App() {
  // ---------- Navigasi ----------
  const [activeTab, setActiveTab] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // ---------- Generator ----------
  const [topic, setTopic] = useState('5 Strategi Kelola Cashflow Usaha Menghadapi Inflasi 2026');
  const [formatType, setFormatType] = useState('carousel');
  const [targetDuration, setTargetDuration] = useState(30);
  const [freshResearch, setFreshResearch] = useState(true);

  // ---------- Eksekusi & polling ----------
  const [currentRunId, setCurrentRunId] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [runData, setRunData] = useState(null);
  const [events, setEvents] = useState([]);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState(null);
  const [videoCaption, setVideoCaption] = useState('');
  const [shareToFeed, setShareToFeed] = useState(true);
  const [currentSlideIndex, setCurrentSlideIndex] = useState(0);
  const [approvingAssetId, setApprovingAssetId] = useState(null);
  const [regeneratingId, setRegeneratingId] = useState(null);
  const [resumingRun, setResumingRun] = useState(false);

  // ---------- Katalog & brand ----------
  const [brand, setBrand] = useState(null);
  const [layouts, setLayouts] = useState([]);
  const [layoutsLoading, setLayoutsLoading] = useState(true);
  const [assets, setAssets] = useState([]);
  const [assetFilter, setAssetFilter] = useState('all');
  const [assetCounts, setAssetCounts] = useState({});
  const [assetsLoading, setAssetsLoading] = useState(true);
  const assetFilterTouched = useRef(false);
  const assetsInitialized = useRef(false);

  const [runs, setRuns] = useState([]);
  const [runsFilter, setRunsFilter] = useState('all');
  const [pendingRunsCount, setPendingRunsCount] = useState(0);
  const [runsLoading, setRunsLoading] = useState(true);

  const [brandForm, setBrandForm] = useState({
    company: '',
    industry: '',
    description: '',
    audience: '',
    phone: '',
    handle: '',
    primary_color: '#0f172a',
    secondary_color: '#f8fafc',
    accent_color: '#10b981',
  });
  const [brandSaving, setBrandSaving] = useState(false);
  const [logoUploading, setLogoUploading] = useState(false);
  const [talentUploading, setTalentUploading] = useState(false);

  // ---------- Enterprise / strategy / analytics ----------
  const [enterpriseProfile, setEnterpriseProfile] = useState(null);
  const [enterpriseLoading, setEnterpriseLoading] = useState(false);
  const [enterpriseError, setEnterpriseError] = useState(null);
  const [profileSaving, setProfileSaving] = useState(false);

  const [strategyCalendar, setStrategyCalendar] = useState([]);
  const [calendarLoading, setCalendarLoading] = useState(false);
  const [calendarRegenerating, setCalendarRegenerating] = useState(false);

  const [analyticsData, setAnalyticsData] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsError, setAnalyticsError] = useState(null);

  // ---------- Akses & status ----------
  const [apiKeyInput, setApiKeyInput] = useState(() => api.getApiKey());
  const [apiKeySet, setApiKeySet] = useState(() => Boolean(api.getApiKey()));
  const [keyRequired, setKeyRequired] = useState(true);
  const [online, setOnline] = useState(true);

  // ---------- Notifikasi ----------
  const previousStatus = useRef({ runId: null, status: null });
  const [toasts, setToasts] = useState([]);
  const dismissToast = useCallback((id) => {
    setToasts((list) => list.filter((toast) => toast.id !== id));
  }, []);
  const notify = useCallback((type, text, title) => {
    const id = ++toastSeq;
    setToasts((list) => [...list.slice(-3), { id, type, text, title }]);
    if (type !== 'error') {
      window.setTimeout(() => {
        setToasts((list) => list.filter((toast) => toast.id !== id));
      }, 6500);
    }
  }, []);

  // ---------- Pengambilan data ----------
  const fetchBrand = useCallback(() => {
    return api.getBrand()
      .then((data) => {
        setBrand(data);
        const lines = data.chrome?.footer?.lines || [];
        setBrandForm({
          company: data.company || '',
          industry: data.industry || '',
          description: data.description || '',
          audience: data.audience || '',
          phone: lines[1] || '',
          handle: lines[0] || '',
          primary_color: data.colors?.primary || '#0f172a',
          secondary_color: data.colors?.secondary || '#f8fafc',
          accent_color: data.colors?.accent || '#10b981',
        });
      })
      .catch((err) => notify('error', `Gagal memuat data brand: ${err.message}`));
  }, [notify]);

  const fetchAssets = useCallback((filter = 'all') => {
    setAssetsLoading(true);
    return api.getAssets(filter)
      .then((res) => {
        setAssets(res.assets || []);
        setAssetCounts(res.counts || {});
        if (!assetsInitialized.current) {
          assetsInitialized.current = true;
          if (!assetFilterTouched.current && filter === 'all' && (res.counts?.pending_review || 0) > 0) {
            setAssetFilter('pending_review');
          }
        }
      })
      .catch((err) => notify('error', `Gagal memuat aset: ${err.message}`))
      .finally(() => setAssetsLoading(false));
  }, [notify]);

  const changeAssetFilter = (key) => {
    assetFilterTouched.current = true;
    setAssetFilter(key);
  };

  const fetchRuns = useCallback(() => {
    setRunsLoading(true);
    return api.getRuns({ limit: 50, status: runsFilter === 'all' ? undefined : runsFilter })
      .then((res) => setRuns(res.runs || []))
      .catch((err) => notify('error', `Gagal memuat riwayat konten: ${err.message}`))
      .finally(() => setRunsLoading(false));
  }, [runsFilter, notify]);

  useEffect(() => {
    fetchBrand();
    api.getLayouts()
      .then((res) => setLayouts(res.layouts || []))
      .catch((err) => notify('error', `Gagal memuat template layout: ${err.message}`))
      .finally(() => setLayoutsLoading(false));
    api.getHealth().then(() => setOnline(true)).catch(() => setOnline(false));
    api.getAuthStatus()
      .then(async (res) => {
        const required = Boolean(res.key_required);
        setKeyRequired(required);
        // Mode lokal: ambil kunci langsung dari backend supaya pengguna tidak
        // perlu menempel X-API-Key manual di halaman Pengaturan.
        if (required && !api.getApiKey()) {
          const devKey = await api.getDevApiKey().catch(() => '');
          if (devKey) {
            api.setApiKey(devKey);
            setApiKeyInput(devKey);
            setApiKeySet(true);
          }
        }
      })
      .catch(() => { /* biarkan default: anggap kunci diperlukan */ });
  }, [fetchBrand, notify]);

  useEffect(() => {
    fetchAssets(assetFilter);
  }, [assetFilter, fetchAssets]);

  useEffect(() => {
    if (activeTab === 'enterprise' && !enterpriseProfile) {
      setEnterpriseLoading(true);
      setEnterpriseError(null);
      api.getEnterpriseProfile()
        .then(setEnterpriseProfile)
        .catch((err) => setEnterpriseError(err.message))
        .finally(() => setEnterpriseLoading(false));
    }
    if (activeTab === 'strategy' && strategyCalendar.length === 0) {
      setCalendarLoading(true);
      api.getStrategyCalendar()
        .then((data) => setStrategyCalendar(data.items || []))
        .catch((err) => notify('error', `Gagal memuat kalender: ${err.message}`))
        .finally(() => setCalendarLoading(false));
    }
    if (activeTab === 'analytics' && !analyticsData) {
      setAnalyticsLoading(true);
      setAnalyticsError(null);
      api.getAnalyticsDashboard()
        .then(setAnalyticsData)
        .catch((err) => setAnalyticsError(err.message))
        .finally(() => setAnalyticsLoading(false));
    }
  }, [activeTab, enterpriseProfile, strategyCalendar.length, analyticsData, notify]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns, isRunning]);

  // Jumlah konten yang menunggu persetujuan (untuk badge navigasi), terpisah dari filter daftar
  useEffect(() => {
    api.getRuns({ limit: 1, status: 'awaiting_approval' })
      .then((res) => setPendingRunsCount(res.total || 0))
      .catch(() => { /* badge bersifat opsional */ });
  }, [isRunning, activeTab, runsFilter]);

  // Pulihkan run terakhir setelah refresh halaman
  useEffect(() => {
    const saved = readLastRunId();
    if (!saved) return undefined;
    let cancelled = false;
    api.getRunStatus(saved)
      .then((res) => {
        if (cancelled) return;
        setFormatType(res.format === 'video' ? 'video' : 'carousel');
        setIsRunning(res.status === 'running');
        setCurrentRunId(saved);
      })
      .catch(() => forgetLastRunId());
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (currentRunId) saveLastRunId(currentRunId);
  }, [currentRunId]);

  // Caption Reels: isi saran server setiap kali run/video berganti
  const suggestedCaption = runData?.video?.suggested_caption || '';
  useEffect(() => {
    setVideoCaption(suggestedCaption);
  }, [currentRunId, suggestedCaption]);

  // Polling status run & event log
  useEffect(() => {
    if (!currentRunId) return undefined;

    let cancelled = false;
    let interval = null;

    const poll = async () => {
      try {
        const [statusRes, eventsRes] = await Promise.all([
          api.getRunStatus(currentRunId),
          api.getRunEvents(currentRunId),
        ]);
        if (cancelled) return;
        setRunData(statusRes);
        setEvents(eventsRes.events || []);

        // Beri tahu pengguna saat status berubah (bukan saat membuka run lama)
        const previous = previousStatus.current;
        if (previous.runId !== currentRunId) {
          previousStatus.current = { runId: currentRunId, status: statusRes.status };
        } else if (previous.status !== statusRes.status && previous.status === 'running') {
          if (statusRes.status === 'ok') {
            notify('success', 'Konten selesai dibuat. Periksa hasilnya sebelum diposting.', 'Selesai');
          } else if (statusRes.status === 'failed') {
            notify('error', statusRes.error || 'Proses gagal. Lihat detail proses AI untuk penyebabnya.', 'Pembuatan konten gagal');
          } else if (statusRes.status === 'awaiting_approval') {
            notify('info', 'AI butuh persetujuan Anda untuk pose foto.', 'Menunggu persetujuan');
          } else if (statusRes.status === 'awaiting_assets') {
            notify('warning', 'Pose foto belum tersedia. Lanjutkan proses untuk mencoba lagi.', 'Butuh foto pose');
          }
          previousStatus.current = { runId: currentRunId, status: statusRes.status };
        } else {
          previousStatus.current = { runId: currentRunId, status: statusRes.status };
        }

        if (TERMINAL_STATUSES.includes(statusRes.status)) {
          if (interval) { clearInterval(interval); interval = null; }
          setIsRunning(false);
        }
      } catch (err) {
        if (!cancelled) console.error('Polling error:', err);
      }
    };

    const start = () => {
      if (isRunning && !interval && !document.hidden) {
        interval = setInterval(poll, POLL_INTERVAL_MS);
      }
    };
    const stop = () => {
      if (interval) { clearInterval(interval); interval = null; }
    };

    const onVisibilityChange = () => {
      if (document.hidden) stop();
      else if (isRunning) { poll(); start(); }
    };

    poll();
    start();
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      cancelled = true;
      stop();
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [currentRunId, isRunning, notify]);

  useEffect(() => {
    if (!sidebarOpen) return undefined;
    const onKey = (event) => { if (event.key === 'Escape') setSidebarOpen(false); };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [sidebarOpen]);

  // ---------- Navigasi ----------
  const navigate = (tab) => {
    setActiveTab(tab);
    setSidebarOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // ---------- Aksi generator ----------
  const resetRun = () => {
    setCurrentRunId(null);
    setRunData(null);
    setEvents([]);
    setPublishResult(null);
    setIsRunning(false);
    setCurrentSlideIndex(0);
    forgetLastRunId();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleGenerate = async (event) => {
    event.preventDefault();
    if (!topic.trim() || isRunning) return;

    setCurrentRunId(null);
    setIsRunning(true);
    setRunData(null);
    setEvents([]);
    setCurrentSlideIndex(0);
    setPublishResult(null);

    try {
      const res = formatType === 'carousel'
        ? await api.generateCarousel(topic, freshResearch)
        : await api.generateVideo(topic, targetDuration, freshResearch);
      setCurrentRunId(res.run_id);
      notify('info', res.message || 'Konten mulai dibuat. Hasil akan muncul otomatis.', 'Diproses AI');
    } catch (err) {
      notify('error', err.message, 'Gagal memulai pembuatan konten');
      setIsRunning(false);
    }
  };

  const handlePublish = async () => {
    if (!currentRunId) return;
    setPublishing(true);
    setPublishResult(null);
    try {
      const isReel = (runData?.format ?? formatType) === 'video';
      const res = await api.publishToInstagram(
        currentRunId,
        isReel ? { caption: videoCaption, share_to_feed: shareToFeed } : undefined
      );
      setPublishResult(res);
      try {
        const eventsRes = await api.getRunEvents(currentRunId);
        setEvents(eventsRes.events || []);
      } catch (err) {
        console.error(err);
      }
      const isOk = res.status === 'published' || res.ok;
      if (isOk) {
        notify('success', res.format === 'reel' ? 'Reels berhasil diposting ke Instagram.' : 'Konten berhasil dikirim ke Instagram.', 'Publikasi berhasil');
      } else {
        notify('error', res.error || 'Terjadi kesalahan saat publikasi.', 'Publikasi gagal');
      }
    } catch (err) {
      notify('error', err.message, 'Publikasi gagal');
    } finally {
      setPublishing(false);
    }
  };

  const refreshRun = async (runId) => {
    const [statusRes, eventsRes] = await Promise.all([api.getRunStatus(runId), api.getRunEvents(runId)]);
    setRunData(statusRes);
    setEvents(eventsRes.events || []);
    return statusRes;
  };

  const openRun = async (runId, format, status) => {
    setCurrentRunId(runId);
    setRunData(null);
    setEvents([]);
    setCurrentSlideIndex(0);
    setPublishResult(null);
    if (format) setFormatType(format === 'video' ? 'video' : 'carousel');
    setIsRunning(status === 'running');
    navigate('generator');
    try {
      const fresh = await refreshRun(runId);
      if (fresh.status === 'running') setIsRunning(true);
    } catch (err) {
      notify('error', `Gagal membuka konten: ${err.message}`);
    }
  };

  const handleApproveAsset = async (assetId, decision = 'approved', assetRunId = null) => {
    setApprovingAssetId(assetId);
    try {
      await api.reviewAsset(assetId, decision);
      fetchAssets(assetFilter);
      fetchRuns();

      const targetRunId = assetRunId || currentRunId;
      const isCurrent = targetRunId && targetRunId === currentRunId;
      let text = `Pose berhasil di${decision === 'approved' ? 'setujui' : 'tolak'}.`;

      if (isCurrent) {
        const fresh = await refreshRun(targetRunId);
        const items = fresh.design?.pending_review || [];
        const waiting = ['awaiting_approval', 'awaiting_assets'].includes(fresh.status);
        const stillPending = items.some((item) => item.status === 'pending_review');
        const anyRejected = items.some((item) => item.status === 'rejected');
        if (waiting && items.length > 0 && !stillPending && !anyRejected) {
          setResumingRun(true);
          await api.resumeRun(targetRunId);
          setIsRunning(true);
          text += ' Semua pose disetujui, proses rendering dilanjutkan.';
        } else if (stillPending) {
          text += ` Masih ada ${items.filter((item) => item.status === 'pending_review').length} pose menunggu keputusan.`;
        } else if (anyRejected) {
          text += ' Ada pose yang ditolak, proses belum bisa dilanjutkan.';
        }
      } else if (targetRunId) {
        text += ' Buka konten terkait di Riwayat Konten untuk melanjutkan.';
      }
      notify('success', text);
    } catch (err) {
      notify('error', err.message, 'Gagal menyimpan keputusan');
    } finally {
      setApprovingAssetId(null);
      setResumingRun(false);
    }
  };

  const handleRegenerate = async (assetId, assetRunId = null) => {
    setRegeneratingId(assetId);
    try {
      const targetRunId = assetRunId || currentRunId;
      const res = await api.regeneratePose(assetId, { runId: targetRunId });
      fetchAssets(assetFilter);
      fetchRuns();
      if (res.mode === 'run' && res.run_id === currentRunId) {
        setIsRunning(true);
        await refreshRun(res.run_id);
      }
      notify(
        'info',
        res.mode === 'run'
          ? 'Pose baru sedang dibuat. Konten akan kembali ke “Menunggu persetujuan” setelah selesai (biasanya 1–2 menit).'
          : 'Pose baru sedang dibuat di Asset Library. Muat ulang daftar aset beberapa saat lagi.'
      );
    } catch (err) {
      notify('error', err.message, 'Gagal membuat ulang pose');
    } finally {
      setRegeneratingId(null);
    }
  };

  const handleResumeRun = async () => {
    if (!currentRunId) return;
    setResumingRun(true);
    try {
      await api.resumeRun(currentRunId);
      setIsRunning(true);
      notify('success', 'Proses dilanjutkan untuk merender hasil final.');
    } catch (err) {
      notify('error', err.message, 'Gagal melanjutkan proses');
    } finally {
      setResumingRun(false);
    }
  };

  // ---------- Brand ----------
  const handleSaveBrand = async (event) => {
    event?.preventDefault?.();
    setBrandSaving(true);
    try {
      await api.updateBrand(brandForm);
      await fetchBrand();
      notify('success', 'Identitas brand dan warna berhasil disimpan.');
    } catch (err) {
      notify('error', err.message, 'Gagal menyimpan brand');
    } finally {
      setBrandSaving(false);
    }
  };

  const handleLogoUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setLogoUploading(true);
    try {
      await api.uploadLogo(file);
      await fetchBrand();
      notify('success', 'Logo berhasil diunggah dan akan dipakai pada konten berikutnya.');
    } catch (err) {
      notify('error', err.message, 'Gagal mengunggah logo');
    } finally {
      setLogoUploading(false);
      event.target.value = '';
    }
  };

  const handleTalentUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setTalentUploading(true);
    try {
      await api.uploadTalentReference(file, 'operator_01');
      await fetchBrand();
      fetchAssets(assetFilter);
      notify('success', 'Foto model berhasil diunggah. AI siap membuat variasi pose.');
    } catch (err) {
      notify('error', err.message, 'Gagal mengunggah foto model');
    } finally {
      setTalentUploading(false);
      event.target.value = '';
    }
  };

  // ---------- Enterprise ----------
  const loadEnterprise = useCallback(() => {
    setEnterpriseLoading(true);
    setEnterpriseError(null);
    return api.getEnterpriseProfile()
      .then(setEnterpriseProfile)
      .catch((err) => {
        setEnterpriseError(err.message);
        notify('error', err.message, 'Gagal memuat profil enterprise');
      })
      .finally(() => setEnterpriseLoading(false));
  }, [notify]);

  const handleSaveEnterprise = async (profile) => {
    setProfileSaving(true);
    try {
      const res = await api.updateEnterpriseProfile(profile);
      setEnterpriseProfile({ ...profile, completeness_score: res.completeness_score ?? profile.completeness_score });
      notify('success', 'Profil enterprise berhasil disimpan.');
    } catch (err) {
      notify('error', err.message, 'Gagal menyimpan profil');
    } finally {
      setProfileSaving(false);
    }
  };

  // ---------- Strategi ----------
  const loadStrategy = useCallback((regenerate = false) => {
    if (regenerate) setCalendarRegenerating(true);
    else setCalendarLoading(true);
    const request = regenerate ? api.regenerateStrategyCalendar() : api.getStrategyCalendar();
    return request
      .then((data) => {
        setStrategyCalendar(data.items || []);
        if (regenerate) notify('success', 'Kalender strategi baru berhasil disusun.');
      })
      .catch((err) => notify('error', err.message, regenerate ? 'Gagal menyusun kalender' : 'Gagal memuat kalender'))
      .finally(() => {
        setCalendarLoading(false);
        setCalendarRegenerating(false);
      });
  }, [notify]);

  const handleStrategyStatus = async (itemId, status) => {
    try {
      await api.updateStrategyItem(itemId, { status });
      setStrategyCalendar((list) => list.map((item) => (item.id === itemId ? { ...item, status } : item)));
      notify('success', status === 'approved' ? 'Item kalender disetujui.' : 'Item kalender ditolak.');
    } catch (err) {
      notify('error', err.message, 'Gagal memperbarui item kalender');
      throw err;
    }
  };

  const handleGenerateFromStrategy = async (itemId) => {
    try {
      const res = await api.generateFromStrategyItem(itemId);
      setStrategyCalendar((list) => list.map((item) => (item.id === itemId ? { ...item, status: 'producing', run_id: res.run_id } : item)));
      openRun(res.run_id, res.format || 'carousel', 'running');
      notify('info', 'Konten dari kalender mulai dibuat.');
    } catch (err) {
      notify('error', err.message, 'Gagal membuat konten dari kalender');
      throw err;
    }
  };

  // ---------- Analitik ----------
  const loadAnalytics = useCallback(() => {
    setAnalyticsLoading(true);
    setAnalyticsError(null);
    return api.getAnalyticsDashboard()
      .then(setAnalyticsData)
      .catch((err) => setAnalyticsError(err.message))
      .finally(() => setAnalyticsLoading(false));
  }, []);

  // ---------- Kunci API ----------
  const saveApiKey = () => {
    api.setApiKey(apiKeyInput);
    const stored = api.getApiKey();
    setApiKeyInput(stored);
    setApiKeySet(Boolean(stored));
    notify(stored ? 'success' : 'info', stored ? 'Kunci API disimpan di browser ini.' : 'Kunci API dihapus dari browser ini.');
  };

  const clearApiKey = () => {
    api.setApiKey('');
    setApiKeyInput('');
    setApiKeySet(false);
    notify('info', 'Kunci API dihapus dari browser ini.');
  };

  // ---------- Render halaman ----------
  const page = (() => {
    switch (activeTab) {
      case 'dashboard':
        return (
          <Dashboard
            brand={brand}
            brandForm={brandForm}
            apiKeySet={apiKeySet}
            apiKeyRequired={keyRequired}
            onNavigate={navigate}
            onOpenRun={openRun}
          />
        );
      case 'generator':
        return (
          <Generator
            topic={topic}
            setTopic={setTopic}
            formatType={formatType}
            setFormatType={setFormatType}
            targetDuration={targetDuration}
            setTargetDuration={setTargetDuration}
            freshResearch={freshResearch}
            setFreshResearch={setFreshResearch}
            isRunning={isRunning}
            runData={runData}
            events={events}
            currentRunId={currentRunId}
            onSubmit={handleGenerate}
            onReset={resetRun}
            onPublish={handlePublish}
            publishing={publishing}
            publishResult={publishResult}
            videoCaption={videoCaption}
            setVideoCaption={setVideoCaption}
            shareToFeed={shareToFeed}
            setShareToFeed={setShareToFeed}
            currentSlideIndex={currentSlideIndex}
            setCurrentSlideIndex={setCurrentSlideIndex}
            pendingItems={runData?.design?.pending_review || []}
            pendingLeft={(runData?.design?.pending_review || []).some((item) => (item.status ? item.status === 'pending_review' : true))}
            approvingAssetId={approvingAssetId}
            regeneratingId={regeneratingId}
            resumingRun={resumingRun}
            onApprove={handleApproveAsset}
            onRegenerate={handleRegenerate}
            onResume={handleResumeRun}
            apiKeySet={apiKeySet}
            apiKeyRequired={keyRequired}
            onOpenSettings={() => navigate('settings')}
          />
        );
      case 'runs':
        return (
          <Runs
            runs={runs}
            runsFilter={runsFilter}
            setRunsFilter={setRunsFilter}
            pendingRunsCount={pendingRunsCount}
            onRefresh={fetchRuns}
            onOpenRun={openRun}
            currentRunId={currentRunId}
            loading={runsLoading}
          />
        );
      case 'assets':
        return (
          <Assets
            assets={assets}
            assetCounts={assetCounts}
            assetFilter={assetFilter}
            onChangeFilter={changeAssetFilter}
            approvingAssetId={approvingAssetId}
            regeneratingId={regeneratingId}
            onApprove={handleApproveAsset}
            onRegenerate={handleRegenerate}
            onOpenRun={(runId) => openRun(runId)}
            onNavigateBrand={() => navigate('brand')}
            loading={assetsLoading}
          />
        );
      case 'strategy':
        return (
          <Strategy
            items={strategyCalendar}
            loading={calendarLoading}
            regenerating={calendarRegenerating}
            onRegenerate={() => loadStrategy(true)}
            onStatusChange={handleStrategyStatus}
            onGenerate={handleGenerateFromStrategy}
          />
        );
      case 'analytics':
        return (
          <Analytics
            analyticsData={analyticsData}
            loading={analyticsLoading}
            error={analyticsError}
            onRefresh={loadAnalytics}
          />
        );
      case 'social':
        return (
          <Social
            brand={brand}
            apiKeySet={apiKeySet}
            apiKeyRequired={keyRequired}
            onNavigateSettings={() => navigate('settings')}
          />
        );
      case 'brand':
        return (
          <BrandSetup
            brand={brand}
            brandForm={brandForm}
            setBrandForm={setBrandForm}
            onSave={handleSaveBrand}
            saving={brandSaving}
            onLogoUpload={handleLogoUpload}
            logoUploading={logoUploading}
            onTalentUpload={handleTalentUpload}
            talentUploading={talentUploading}
          />
        );
      case 'enterprise':
        return (
          <Enterprise
            profile={enterpriseProfile}
            setProfile={setEnterpriseProfile}
            onSave={handleSaveEnterprise}
            saving={profileSaving}
            loading={enterpriseLoading}
            error={enterpriseError}
            onReload={loadEnterprise}
          />
        );
      case 'layouts':
        return <Layouts layouts={layouts} loading={layoutsLoading} />;
      case 'settings':
        return (
          <Settings
            apiKeyInput={apiKeyInput}
            setApiKeyInput={setApiKeyInput}
            apiKeySet={apiKeySet}
            apiKeyRequired={keyRequired}
            onSaveApiKey={saveApiKey}
            onClearApiKey={clearApiKey}
            online={online}
          />
        );
      default:
        return null;
    }
  })();

  return (
    <div className="min-h-screen bg-canvas">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-brand-700 focus:shadow-popover"
      >
        Lewati ke konten utama
      </a>

      {/* Sidebar desktop */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line bg-surface lg:block">
        <Sidebar
          activeTab={activeTab}
          onNavigate={navigate}
          badges={{ pendingAssets: assetCounts.pending_review || 0, pendingRuns: pendingRunsCount }}
          brandName={brandForm.company || brand?.company}
          online={online}
        />
      </aside>

      {/* Drawer mobile */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-[60] lg:hidden">
          <div
            className="absolute inset-0 bg-[#101828]/45 backdrop-blur-[2px] animate-fade-in"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0 w-[17.5rem] max-w-[85%] shadow-drawer animate-slide-up">
            <Sidebar
              activeTab={activeTab}
              onNavigate={navigate}
              badges={{ pendingAssets: assetCounts.pending_review || 0, pendingRuns: pendingRunsCount }}
              brandName={brandForm.company || brand?.company}
              online={online}
              onClose={() => setSidebarOpen(false)}
            />
          </div>
        </div>
      )}

      <div className="lg:pl-64">
        <Topbar
          meta={PAGE_META[activeTab]}
          onMenu={() => setSidebarOpen(true)}
          brandName={brandForm.company || brand?.company}
          apiKeySet={apiKeySet}
          apiKeyRequired={keyRequired}
          onOpenSettings={() => navigate('settings')}
        />

        <main id="main-content" className="mx-auto w-full max-w-[1400px] px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
          {page}
        </main>

        <footer className="mx-auto w-full max-w-[1400px] px-4 pb-8 pt-2 sm:px-6 lg:px-8">
          <div className="flex flex-col items-center justify-between gap-1.5 border-t border-line pt-4 text-[11px] text-ink-subtle sm:flex-row">
            <p>GTNIC 2026 · Asisten pemasaran AI untuk UMKM</p>
            <p className="flex items-center gap-1.5">
              <span className={online ? 'h-1.5 w-1.5 rounded-full bg-success-500' : 'h-1.5 w-1.5 rounded-full bg-danger-500'} aria-hidden="true" />
              {online ? 'Backend terhubung' : 'Backend tidak terdeteksi'}
            </p>
          </div>
        </footer>
      </div>

      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
