import { useMemo, useState } from 'react';
import {
  BarChart3,
  Bookmark,
  Eye,
  ExternalLink,
  Heart,
  Info,
  MessageSquare,
  RefreshCw,
  TrendingUp,
} from 'lucide-react';
import { Alert, Badge, Button, Card, CardHeader, EmptyState, PageHeader, StatCard } from '../components/ui';
import { BarChart } from '../components/Chart';
import { fmtCompact, fmtNumber, timeAgo, truncate } from '../lib/format';
import { cn } from '../lib/utils';

const METRICS = [
  { key: 'reach', label: 'Jangkauan' },
  { key: 'engagement', label: 'Interaksi' },
  { key: 'saves', label: 'Simpanan' },
];

const CONFIDENCE_TONE = { high: 'success', medium: 'warning', low: 'neutral' };

export default function Analytics({ analyticsData, loading, error, onRefresh }) {
  const [metric, setMetric] = useState('reach');

  const posts = useMemo(() => analyticsData?.posts || [], [analyticsData]);
  const insights = useMemo(() => analyticsData?.insights || [], [analyticsData]);
  const summary = analyticsData?.summary;

  const chartData = useMemo(
    () =>
      [...posts].reverse().map((post) => ({
        ...post,
        engagement: (post.likes || 0) + (post.comments || 0) + (post.shares || 0) + (post.saves || 0),
      })),
    [posts]
  );

  const avgReach = summary?.total_posts_tracked ? Math.round((summary.total_reach || 0) / summary.total_posts_tracked) : 0;
  const engagementRate =
    summary?.total_reach > 0 ? ((summary.total_engagement / summary.total_reach) * 100).toFixed(1) : null;

  if (loading && !analyticsData) {
    return (
      <div className="space-y-4">
        <PageHeader title="Analitik" description="Memuat data performa konten…" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="card h-28 animate-pulse" aria-hidden="true" />
          ))}
        </div>
        <div className="card h-64 animate-pulse" aria-hidden="true" />
      </div>
    );
  }

  if (error && !analyticsData) {
    return (
      <div className="space-y-4">
        <PageHeader title="Analitik" description="Ukur performa konten dan lihat rekomendasi berikutnya." />
        <EmptyState
          icon={BarChart3}
          title="Data analitik gagal dimuat"
          description={error}
          action={<Button icon={RefreshCw} onClick={onRefresh}>Coba lagi</Button>}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Analitik performa"
        description="Ringkasan observasional dari metrik yang tercatat. Sampel kecil atau data simulasi bukan bukti sebab-akibat."
        actions={
          <Button variant="secondary" size="sm" icon={RefreshCw} onClick={onRefresh} loading={loading}>
            Muat ulang
          </Button>
        }
      />

      {summary && (
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={summary.is_simulated ? 'warning' : 'success'}>
            {summary.is_simulated ? 'Sebagian data simulasi' : 'Data Instagram nyata'}
          </Badge>
          <Badge tone="neutral" className="bg-canvas">
            Sumber: {summary.data_source || 'belum ada'}
          </Badge>
          {summary.last_sync ? (
            <span className="text-xs text-ink-muted">Sinkron terakhir {timeAgo(summary.last_sync)}</span>
          ) : (
            <span className="text-xs text-ink-muted">Belum ada sinkronisasi metrik</span>
          )}
          {summary.pending_ingestion > 0 && (
            <Badge tone="warning">{summary.pending_ingestion} postingan menunggu data</Badge>
          )}
        </div>
      )}

      {summary?.is_simulated && (
        <Alert tone="warning">
          Sebagian angka di halaman ini dihasilkan oleh data simulasi bawaan sistem untuk keperluan demonstrasi.
          Angka tersebut tidak mewakili performa nyata akun Instagram Anda.
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Postingan terpantau" value={fmtNumber(summary?.total_posts_tracked ?? 0)} helper="Konten yang punya catatan metrik" icon={BarChart3} />
        <StatCard label="Total jangkauan" value={fmtCompact(summary?.total_reach ?? 0)} helper={`Rata-rata ${fmtCompact(avgReach)} per postingan`} icon={Eye} tone="brand" />
        <StatCard label="Total interaksi" value={fmtCompact(summary?.total_engagement ?? 0)} helper={engagementRate ? `Rasio interaksi ${engagementRate}%` : 'Belum cukup data untuk rasio'} icon={Heart} tone="success" />
        <StatCard label="Total simpanan" value={fmtCompact(summary?.total_saves ?? 0)} helper="Indikator konten dianggap berguna" icon={Bookmark} tone="neutral" />
      </div>

      <Card>
        <CardHeader
          title="Performa per postingan"
          description="Grafik diambil dari catatan metrik tiap konten."
          icon={TrendingUp}
          actions={
            <div className="inline-flex rounded-lg border border-line bg-canvas p-0.5">
              {METRICS.map((option) => (
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
          <BarChart data={chartData} metric={metric} height={220} emptyLabel="Belum ada metrik untuk digambarkan." />
        </div>
      </Card>

      {/* Insights */}
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink">Rekomendasi untuk konten berikutnya</h2>
          <span className="text-xs text-ink-muted">{insights.length} rekomendasi</span>
        </div>
        {insights.length === 0 ? (
          <Card className="p-5">
            <p className="text-sm text-ink-muted">
              Belum ada rekomendasi. Rekomendasi muncul setelah cukup banyak metrik terkumpul dari konten yang tayang.
            </p>
          </Card>
        ) : (
          <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {insights.map((insight) => {
              const confidence = String(insight.confidence || '').toLowerCase();
              const sample = insight.data_points?.sample_size;
              return (
                <li key={insight.id} className="card flex flex-col gap-2 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-semibold leading-snug text-ink">{insight.title}</p>
                    <Badge tone={CONFIDENCE_TONE[confidence] || 'neutral'}>
                      Keyakinan {confidence || 'tidak diketahui'}
                    </Badge>
                  </div>
                  <p className="text-xs leading-relaxed text-ink-muted">{insight.observation}</p>
                  <div className="rounded-xl border border-brand-200 bg-brand-50 p-3">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-brand-700">Saran tindakan</p>
                    <p className="mt-0.5 text-xs leading-relaxed text-brand-900">{insight.recommended_action}</p>
                  </div>
                  <div className="mt-auto flex flex-wrap items-center gap-2 text-[11px] text-ink-subtle">
                    <span className={cn('inline-flex items-center gap-1', insight.applied_to_strategy && 'text-success-700')}>
                      {insight.applied_to_strategy ? 'Sudah dipakai di kalender' : 'Belum dipakai di kalender'}
                    </span>
                    {sample !== undefined && sample !== null && <span>· sampel {sample} data</span>}
                    {insight.data_points?.is_simulated && <span>· simulasi</span>}
                    {insight.created_at && <span>· {insight.created_at}</span>}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Posts */}
      <Card>
        <CardHeader title="Rincian metrik per postingan" description="Nilai kosong berarti metrik belum tersedia dari Instagram." icon={BarChart3} />
        {posts.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={Info}
              title="Belum ada postingan terpantau"
              description="Metrik akan terisi setelah konten dipublikasikan dan data diambil dari Instagram."
              className="border-0 bg-transparent"
            />
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line bg-canvas text-xs uppercase tracking-wide text-ink-muted">
                  <tr>
                    <th scope="col" className="px-4 py-2.5 font-semibold">Tanggal</th>
                    <th scope="col" className="px-4 py-2.5 font-semibold">Topik</th>
                    <th scope="col" className="px-4 py-2.5 font-semibold">Pilar</th>
                    <th scope="col" className="px-4 py-2.5 text-right font-semibold">Reach</th>
                    <th scope="col" className="px-4 py-2.5 text-right font-semibold">Likes</th>
                    <th scope="col" className="px-4 py-2.5 text-right font-semibold">Komentar</th>
                    <th scope="col" className="px-4 py-2.5 text-right font-semibold">Simpan</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {posts.map((post) => (
                    <tr key={post.id} className="transition hover:bg-canvas/70">
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-muted">{post.date || '—'}</td>
                      <td className="max-w-[18rem] px-4 py-3">
                        <p className="truncate font-medium text-ink">{post.topic}</p>
                        <p className="mt-0.5 flex items-center gap-1.5 text-[11px] uppercase text-ink-subtle">
                          {post.format} · {post.is_simulated ? 'simulasi' : post.ingestion_status || 'tersedia'}
                          {post.permalink && (
                            <a href={post.permalink} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-brand-700 hover:underline">
                              <ExternalLink className="h-3 w-3" aria-hidden="true" /> lihat
                            </a>
                          )}
                        </p>
                      </td>
                      <td className="px-4 py-3 text-xs text-ink-muted">{post.pillar || '—'}</td>
                      <td className="px-4 py-3 text-right font-medium text-ink">{fmtNumber(post.reach)}</td>
                      <td className="px-4 py-3 text-right text-ink-muted">{fmtNumber(post.likes)}</td>
                      <td className="px-4 py-3 text-right text-ink-muted">{fmtNumber(post.comments)}</td>
                      <td className="px-4 py-3 text-right text-ink-muted">{fmtNumber(post.saves)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <ul className="divide-y divide-line md:hidden">
              {posts.map((post) => (
                <li key={post.id} className="p-4">
                  <p className="text-sm font-medium leading-snug text-ink">{truncate(post.topic, 90)}</p>
                  <p className="mt-0.5 text-[11px] uppercase text-ink-subtle">
                    {post.date || 'tanggal tidak tersedia'} · {post.format} {post.is_simulated ? '· simulasi' : ''}
                  </p>
                  <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
                    <div className="flex items-center justify-between rounded-lg bg-canvas px-2.5 py-1.5">
                      <dt className="text-ink-muted">Reach</dt>
                      <dd className="font-semibold text-ink">{fmtNumber(post.reach)}</dd>
                    </div>
                    <div className="flex items-center justify-between rounded-lg bg-canvas px-2.5 py-1.5">
                      <dt className="flex items-center gap-1 text-ink-muted"><Heart className="h-3 w-3" aria-hidden="true" />Likes</dt>
                      <dd className="font-semibold text-ink">{fmtNumber(post.likes)}</dd>
                    </div>
                    <div className="flex items-center justify-between rounded-lg bg-canvas px-2.5 py-1.5">
                      <dt className="flex items-center gap-1 text-ink-muted"><MessageSquare className="h-3 w-3" aria-hidden="true" />Komen</dt>
                      <dd className="font-semibold text-ink">{fmtNumber(post.comments)}</dd>
                    </div>
                    <div className="flex items-center justify-between rounded-lg bg-canvas px-2.5 py-1.5">
                      <dt className="flex items-center gap-1 text-ink-muted"><Bookmark className="h-3 w-3" aria-hidden="true" />Simpan</dt>
                      <dd className="font-semibold text-ink">{fmtNumber(post.saves)}</dd>
                    </div>
                  </dl>
                  {post.permalink && (
                    <a href={post.permalink} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline">
                      <ExternalLink className="h-3 w-3" aria-hidden="true" /> Lihat postingan
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>
    </div>
  );
}
