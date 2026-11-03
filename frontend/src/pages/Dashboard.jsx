import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowRight,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  Circle,
  Clock,
  Eye,
  Image as ImageIcon,
  Layers,
  Play,
  RefreshCw,
  Share2,
  Sparkles,
  TrendingUp,
  Users,
} from 'lucide-react';
import { api } from '../api';
import { Badge, Button, Card, CardHeader, EmptyState, LoadingCards, PageHeader, StatCard, StatusBadge } from '../components/ui';
import { BarChart } from '../components/Chart';
import {
  fmtCompact,
  fmtNumber,
  fmtTime,
  runStatusMeta,
  strategyStatusMeta,
  timeAgo,
} from '../lib/format';
import { cn } from '../lib/utils';

const greeting = () => {
  const hour = new Date().getHours();
  if (hour < 11) return 'Selamat pagi';
  if (hour < 15) return 'Selamat siang';
  if (hour < 19) return 'Selamat sore';
  return 'Selamat malam';
};

function ChecklistItem({ done, label, description, actionLabel, onAction }) {
  return (
    <li className="flex items-start gap-3">
      {done ? (
        <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success-500" aria-hidden="true" />
      ) : (
        <Circle className="mt-0.5 h-5 w-5 shrink-0 text-ink-subtle" aria-hidden="true" />
      )}
      <div className="min-w-0 flex-1">
        <p className={cn('text-sm font-medium', done ? 'text-ink-muted line-through' : 'text-ink')}>{label}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{description}</p>
      </div>
      {!done && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-brand-700 transition hover:bg-brand-50"
        >
          {actionLabel || 'Atur'}
        </button>
      )}
    </li>
  );
}

export default function Dashboard({ brand, brandForm, apiKeySet, apiKeyRequired = true, onNavigate, onOpenRun }) {
  const [data, setData] = useState({
    runs: null,
    assets: null,
    analytics: null,
    ops: null,
    strategy: null,
    notifications: null,
  });
  const [loading, setLoading] = useState({ runs: true, assets: true, analytics: true, ops: true, strategy: true, notifications: true });
  const [errors, setErrors] = useState({});
  const [refreshing, setRefreshing] = useState(false);
  const [metric, setMetric] = useState('reach');

  const load = useCallback(async () => {
    const tasks = [
      ['runs', () => api.getRuns({ limit: 50 })],
      ['assets', () => api.getAssets('all')],
      ['analytics', () => api.getAnalyticsDashboard()],
      ['ops', () => api.getOpsStatus()],
      ['strategy', () => api.getStrategyCalendar()],
      ['notifications', () => api.getNotifications({ limit: 6 })],
    ];
    await Promise.all(
      tasks.map(async ([key, fn]) => {
        try {
          const result = await fn();
          setData((prev) => ({ ...prev, [key]: result }));
          setErrors((prev) => ({ ...prev, [key]: null }));
        } catch (err) {
          setErrors((prev) => ({ ...prev, [key]: err.message }));
        } finally {
          setLoading((prev) => ({ ...prev, [key]: false }));
        }
      })
    );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = async () => {
    setRefreshing(true);
    setLoading((prev) => Object.fromEntries(Object.keys(prev).map((key) => [key, true])));
    await load();
    setRefreshing(false);
  };

  const runs = useMemo(() => data.runs?.runs || [], [data.runs]);
  const totalRuns = data.runs?.total ?? 0;
  const awaitingRuns = useMemo(() => runs.filter((r) => r.status === 'awaiting_approval' || r.status === 'awaiting_assets'), [runs]);
  const pendingAssets = data.assets?.counts?.pending_review || 0;
  const analytics = data.analytics;
  const ops = data.ops;
  const strategyItems = useMemo(() => data.strategy?.items || [], [data.strategy]);
  const upcoming = useMemo(() => {
    const order = ['draft', 'awaiting_approval', 'approved', 'approved_to_publish', 'scheduled'];
    return [...strategyItems]
      .filter((item) => order.includes(item.status))
      .sort((a, b) => String(a.plan_date).localeCompare(String(b.plan_date)))
      .slice(0, 3);
  }, [strategyItems]);

  const recentRuns = runs.slice(0, 4);
  const totalReach = analytics?.summary?.total_reach;
  const totalEngagement = analytics?.summary?.total_engagement;
  const isSimulated = analytics?.summary?.is_simulated;
  const instagramReady = ops?.analytics_ingestion?.instagram_configured;
  const schedulerEnabled = ops?.scheduler?.enabled;

  const chartData = useMemo(() => {
    const posts = [...(analytics?.posts || [])].reverse();
    return posts.map((post) => ({
      ...post,
      engagement: (post.likes || 0) + (post.comments || 0) + (post.shares || 0) + (post.saves || 0),
    }));
  }, [analytics]);

  const checklist = [
    {
      done: Boolean(brandForm.company?.trim()),
      label: 'Lengkapi identitas usaha',
      description: 'Nama usaha, industri, dan kontak dipakai AI agar konten terasa personal.',
      actionLabel: 'Isi brand',
      onAction: () => onNavigate('brand'),
    },
    {
      done: Boolean(brand?.has_logo),
      label: 'Unggah logo usaha',
      description: 'Logo otomatis muncul di setiap slide carousel.',
      actionLabel: 'Unggah',
      onAction: () => onNavigate('brand'),
    },
    {
      done: Boolean(brand?.has_talent_ref),
      label: 'Unggah foto model (opsional)',
      description: 'AI membuat variasi pose dari satu foto asli Anda.',
      actionLabel: 'Unggah',
      onAction: () => onNavigate('brand'),
    },
    {
      done: strategyItems.length > 0,
      label: 'Siapkan kalender strategi',
      description: 'Rencana konten 7 hari agar posting lebih konsisten.',
      actionLabel: 'Buka',
      onAction: () => onNavigate('strategy'),
    },
    {
      done: totalRuns > 0,
      label: 'Buat konten pertama',
      description: 'Cukup tulis satu topik, AI menyiapkan sisanya.',
      actionLabel: 'Mulai',
      onAction: () => onNavigate('generator'),
    },
  ];
  const checklistDone = checklist.filter((item) => item.done).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${greeting()}, ${brandForm.company?.trim() || 'Sahabat UMKM'} 👋`}
        description="Ini ringkasan aktivitas pemasaran Anda hari ini. Semua angka di bawah berasal dari data aplikasi Anda sendiri."
        actions={
          <Button variant="secondary" size="sm" icon={RefreshCw} loading={refreshing} onClick={refresh}>
            Muat ulang
          </Button>
        }
      />

      {/* Hero + checklist */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="relative overflow-hidden border-brand-200 bg-brand-50 p-6 lg:col-span-2">
          <div className="pointer-events-none absolute -right-10 -top-12 h-44 w-44 rounded-full bg-brand-200/50" aria-hidden="true" />
          <div className="relative">
            <Badge tone="brand" className="bg-white/70">
              <Sparkles className="h-3 w-3" aria-hidden="true" /> Asisten Pemasaran AI
            </Badge>
            <h2 className="mt-3 max-w-lg text-xl font-bold leading-snug text-ink sm:text-2xl">
              Siap membuat konten yang konsisten untuk usaha Anda?
            </h2>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink-muted">
              Tulis satu topik, lalu AI akan meriset, menyusun, dan mendesain carousel atau video Reels.
              Anda tetap memegang kendali penuh sebelum konten dipublikasikan.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button icon={Sparkles} onClick={() => onNavigate('generator')}>
                Buat konten baru
              </Button>
              <Button variant="secondary" icon={CalendarDays} onClick={() => onNavigate('strategy')}>
                Lihat kalender
              </Button>
            </div>
            <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { label: 'Konten dibuat', value: data.runs ? totalRuns : '—' },
                { label: 'Menunggu review', value: data.runs ? awaitingRuns.length : '—' },
                { label: 'Aset menunggu', value: data.assets ? pendingAssets : '—' },
                { label: 'Item kalender', value: data.strategy ? strategyItems.length : '—' },
              ].map((stat) => (
                <div key={stat.label} className="rounded-xl bg-white/70 px-3 py-2">
                  <dt className="text-[11px] font-medium text-ink-muted">{stat.label}</dt>
                  <dd className="text-lg font-bold text-ink">{stat.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">Persiapan akun</h2>
            <span className="text-xs font-semibold text-brand-700">
              {checklistDone}/{checklist.length}
            </span>
          </div>
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-soft">
            <div
              className="h-full rounded-full bg-brand-400 transition-all"
              style={{ width: `${(checklistDone / checklist.length) * 100}%` }}
            />
          </div>
          <ul className="mt-4 space-y-3">
            {checklist.map((item) => (
              <ChecklistItem key={item.label} {...item} />
            ))}
          </ul>
        </Card>
      </div>

      {/* Statistik */}
      {loading.runs || loading.analytics ? (
        <LoadingCards count={4} />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Total konten dibuat"
            value={fmtNumber(totalRuns)}
            helper={[
              `${runs.filter((r) => r.status === 'ok').length} selesai`,
              `${awaitingRuns.length} menunggu review`,
              runs.some((r) => r.status === 'failed') ? `${runs.filter((r) => r.status === 'failed').length} gagal` : null,
            ].filter(Boolean).join(' · ')}
            icon={Layers}
            tone="brand"
          />
          <StatCard
            label="Menunggu tindakan Anda"
            value={fmtNumber(awaitingRuns.length + pendingAssets)}
            helper={
              awaitingRuns.length + pendingAssets > 0
                ? 'Setujui konten atau pose agar proses berlanjut'
                : 'Tidak ada yang perlu ditinjau saat ini'
            }
            icon={Clock}
            tone={awaitingRuns.length + pendingAssets > 0 ? 'warning' : 'success'}
            action={
              awaitingRuns.length + pendingAssets > 0 ? (
                <Button size="xs" variant="secondary" onClick={() => onNavigate(awaitingRuns.length > 0 ? 'runs' : 'assets')}>
                  Tinjau sekarang
                </Button>
              ) : null
            }
          />
          <StatCard
            label="Jangkauan (reach)"
            value={errors.analytics ? '—' : fmtCompact(totalReach)}
            helper={
              errors.analytics
                ? errors.analytics
                : analytics?.summary?.total_posts_tracked
                  ? `${analytics.summary.total_posts_tracked} postingan terpantau${isSimulated ? ' · data simulasi' : ''}`
                  : 'Belum ada metrik terkumpul'
            }
            icon={Eye}
            tone="brand"
          />
          <StatCard
            label="Interaksi (engagement)"
            value={errors.analytics ? '—' : fmtCompact(totalEngagement)}
            helper={
              analytics?.summary?.last_sync
                ? `Sinkron terakhir ${timeAgo(analytics.summary.last_sync)}`
                : 'Metrik diperbarui setelah konten tayang'
            }
            icon={TrendingUp}
            tone="success"
          />
        </div>
      )}

      {/* Chart + status */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Performa postingan"
            description="Diambil dari metrik Instagram yang tercatat di aplikasi ini."
            icon={BarChart3}
            actions={
              <div className="inline-flex rounded-lg border border-line bg-canvas p-0.5">
                {[
                  { key: 'reach', label: 'Jangkauan' },
                  { key: 'engagement', label: 'Interaksi' },
                ].map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    onClick={() => setMetric(option.key)}
                    className={cn(
                      'rounded-md px-2.5 py-1 text-xs font-semibold transition',
                      metric === option.key ? 'bg-surface text-ink shadow-card' : 'text-ink-muted hover:text-ink'
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            }
          />
          <div className="p-5">
            {loading.analytics ? (
              <div className="h-48 animate-pulse rounded-xl bg-soft" aria-busy="true" />
            ) : errors.analytics ? (
              <EmptyState
                icon={BarChart3}
                title="Metrik belum bisa dimuat"
                description={errors.analytics}
                action={<Button size="sm" variant="secondary" icon={RefreshCw} onClick={refresh}>Coba lagi</Button>}
              />
            ) : (
              <>
                <BarChart data={chartData} metric={metric} height={200} emptyLabel="Belum ada metrik postingan." />
                {isSimulated && (
                  <p className="mt-3 rounded-lg bg-warning-50 px-3 py-2 text-xs leading-relaxed text-warning-700">
                    Sebagian data analitik merupakan simulasi transparan dari sistem, bukan hasil nyata Instagram.
                  </p>
                )}
              </>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Status layanan & koneksi" description="Kondisi nyata integrasi yang dipakai aplikasi." icon={Share2} />
          <div className="space-y-3 p-5">
            {[
              {
                label: 'Server AI',
                value: errors.ops ? 'Tidak terhubung' : ops ? 'Terhubung' : 'Memeriksa…',
                ok: !errors.ops && Boolean(ops),
                hint: errors.ops || 'Antarmuka berhasil menghubungi backend.',
              },
              {
                label: 'Kunci API',
                value: !apiKeyRequired ? 'Tidak diperlukan' : apiKeySet ? 'Tersimpan di browser' : 'Belum diatur',
                ok: apiKeySet || !apiKeyRequired,
                hint: !apiKeyRequired
                  ? 'Server lokal berjalan dalam mode development terbuka, jadi aksi mengubah data tetap diizinkan.'
                  : apiKeySet
                    ? 'Aksi yang mengubah data diizinkan.'
                    : 'Atur di halaman Pengaturan untuk bisa menyimpan & memposting.',
                action: apiKeyRequired && !apiKeySet ? () => onNavigate('settings') : undefined,
              },
              {
                label: 'Instagram',
                value: instagramReady ? 'Akun terkonfigurasi' : 'Belum terkonfigurasi',
                ok: Boolean(instagramReady),
                hint: instagramReady
                  ? 'Publikasi otomatis dapat dijalankan backend.'
                  : 'Isi kredensial Instagram di konfigurasi backend untuk mengaktifkan publikasi.',
              },
              {
                label: 'Penjadwal otomatis',
                value: schedulerEnabled ? (ops?.scheduler?.active ? 'Aktif' : 'Aktif, menunggu giliran') : 'Nonaktif',
                ok: Boolean(schedulerEnabled),
                hint: schedulerEnabled
                  ? 'Konten terjadwal dapat diposting otomatis.'
                  : 'Posting dijalankan manual dari halaman konten.',
              },
            ].map((row) => (
              <div key={row.label} className="rounded-xl border border-line bg-canvas px-3.5 py-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-ink">{row.label}</p>
                  <span className={cn('flex items-center gap-1.5 text-xs font-semibold', row.ok ? 'text-success-700' : 'text-warning-700')}>
                    <span className={cn('h-2 w-2 rounded-full', row.ok ? 'bg-success-500' : 'bg-warning-500')} aria-hidden="true" />
                    {row.value}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-ink-muted">{row.hint}</p>
                {row.action && !row.ok && (
                  <button type="button" onClick={row.action} className="mt-1 text-xs font-semibold text-brand-700 hover:underline">
                    Atur sekarang →
                  </button>
                )}
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Recent runs + calendar + notifications */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Konten terbaru"
            description="Klik untuk membuka pratinjau dan melanjutkan proses."
            icon={Sparkles}
            actions={
              <Button size="xs" variant="ghost" iconRight={ArrowRight} onClick={() => onNavigate('runs')}>
                Semua konten
              </Button>
            }
          />
          <div className="p-3 sm:p-4">
            {loading.runs ? (
              <div className="space-y-2" aria-busy="true">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-16 animate-pulse rounded-xl bg-soft" />
                ))}
              </div>
            ) : recentRuns.length === 0 ? (
              <EmptyState
                icon={Sparkles}
                title="Belum ada konten"
                description="Mulai dengan menuliskan satu topik. AI akan menyiapkan carousel atau video untuk Anda."
                action={<Button size="sm" icon={Sparkles} onClick={() => onNavigate('generator')}>Buat konten pertama</Button>}
              />
            ) : (
              <ul className="space-y-2">
                {recentRuns.map((run) => {
                  const meta = runStatusMeta(run.status);
                  return (
                    <li key={run.run_id}>
                      <button
                        type="button"
                        onClick={() => onOpenRun(run.run_id, run.format, run.status)}
                        className="flex w-full items-center gap-3 rounded-xl border border-line bg-surface p-2.5 text-left transition hover:border-brand-300 hover:bg-canvas"
                      >
                        <span className="flex h-14 w-12 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-canvas">
                          {run.thumbnail_url ? (
                            <img src={run.thumbnail_url} alt="" className="h-full w-full object-cover" loading="lazy" />
                          ) : run.format === 'video' ? (
                            <Play className="h-5 w-5 text-brand-500" aria-hidden="true" />
                          ) : (
                            <ImageIcon className="h-5 w-5 text-ink-subtle" aria-hidden="true" />
                          )}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-ink">{run.topic}</span>
                          <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-ink-muted">
                            <Badge tone="neutral" className="bg-canvas">
                              {run.format === 'video' ? 'Reels' : 'Carousel'}
                            </Badge>
                            <span>{fmtTime(run.started_at)}</span>
                            {run.pending_review_count > 0 && (
                              <span className="font-semibold text-warning-700">
                                {run.pending_review_count} pose menunggu
                              </span>
                            )}
                          </span>
                        </span>
                        <StatusBadge meta={meta} dot className="shrink-0" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Rencana konten berikutnya"
              description="Dari kalender strategi Anda."
              icon={CalendarDays}
              actions={
                <Button size="xs" variant="ghost" onClick={() => onNavigate('strategy')}>
                  Kelola
                </Button>
              }
            />
            <div className="p-4">
              {loading.strategy ? (
                <div className="space-y-2" aria-busy="true">
                  {[0, 1].map((i) => <div key={i} className="h-14 animate-pulse rounded-xl bg-soft" />)}
                </div>
              ) : upcoming.length === 0 ? (
                <EmptyState
                  icon={CalendarDays}
                  title="Kalender masih kosong"
                  description="Buat rencana 7 hari agar konten lebih teratur."
                  className="border-0 bg-transparent py-6"
                  action={<Button size="xs" variant="secondary" onClick={() => onNavigate('strategy')}>Buka kalender</Button>}
                />
              ) : (
                <ul className="space-y-2.5">
                  {upcoming.map((item) => (
                    <li key={item.id} className="rounded-xl border border-line bg-canvas p-3">
                      <div className="flex items-center justify-between gap-2 text-xs text-ink-muted">
                        <span className="font-medium">
                          {item.plan_date}
                          {item.scheduled_slot ? ` · ${item.scheduled_slot}` : ''}
                        </span>
                        <StatusBadge meta={strategyStatusMeta(item.status)} />
                      </div>
                      <p className="mt-1 line-clamp-2 text-sm font-medium text-ink">{item.topic}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Kabar terbaru" icon={Users} />
            <div className="p-4">
              {loading.notifications ? (
                <div className="h-16 animate-pulse rounded-xl bg-soft" aria-busy="true" />
              ) : (data.notifications?.items || []).length === 0 ? (
                <p className="text-sm text-ink-muted">Belum ada kabar baru dari sistem.</p>
              ) : (
                <ul className="space-y-3">
                  {(data.notifications?.items || []).slice(0, 4).map((item) => (
                    <li key={item.id} className="flex items-start gap-2.5">
                      <span
                        className={cn(
                          'mt-1.5 h-2 w-2 shrink-0 rounded-full',
                          item.is_read ? 'bg-line' : 'bg-brand-400'
                        )}
                        aria-hidden="true"
                      />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-ink">{item.title}</p>
                        <p className="line-clamp-2 text-xs leading-relaxed text-ink-muted">{item.message}</p>
                        <p className="mt-0.5 text-[11px] text-ink-subtle">{timeAgo(item.created_at)}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
