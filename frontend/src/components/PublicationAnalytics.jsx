import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Bookmark, ChevronRight, Eye, ExternalLink, Heart, MessageSquare, RefreshCw, Share2, TrendingUp } from 'lucide-react';
import { Alert, Badge, Button, Card, CardHeader, EmptyState, StatCard } from '../components/ui';
import { fmtNumber, timeAgo, truncate } from '../lib/format';
import { cn } from '../lib/utils';
import { api } from '../api';
import { InstagramIcon } from './BrandIcons';

// Metrik yang ditampilkan. `key` cocok dengan blok `metrics` dari
// GET /api/v1/analytics/publications/{id}; nilai null/undefined = BELUM TERSEDIA
// dari Instagram, sehingga ditampilkan "—" dan TIDAK dianggap nol.
const METRIC_FIELDS = [
  { key: 'reach', label: 'Reach', icon: Eye },
  { key: 'impressions', label: 'Impressions', icon: TrendingUp },
  { key: 'views', label: 'Views/Plays', icon: Eye },
  { key: 'likes', label: 'Likes', icon: Heart },
  { key: 'comments', label: 'Comments', icon: MessageSquare },
  { key: 'shares', label: 'Shares', icon: Share2 },
  { key: 'saves', label: 'Saves', icon: Bookmark },
];

const isMissing = (value) => value === null || value === undefined;

function MetricTile({ label, icon: Icon, value, available }) {
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2.5">
      <dt className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-subtle">
        {Icon && <Icon className="h-3 w-3" aria-hidden="true" />}
        {label}
      </dt>
      <dd className={cn('mt-1 text-base font-semibold', available ? 'text-ink' : 'text-ink-subtle')}>
        {available ? fmtNumber(value) : '—'}
      </dd>
      {!available && <p className="text-[10px] text-ink-subtle">belum tersedia</p>}
    </div>
  );
}

function PublicationDetail({ pubId, onClose, onIngestSuccess }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [ingesting, setIngesting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDetail(await api.getPublicationAnalytics(pubId));
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [pubId]);

  useEffect(() => { load(); }, [load]);

  // Ambil metrik TERBARU dari Instagram untuk postingan ini (bukan dummy).
  const ingest = async () => {
    setIngesting(true);
    try {
      await api.ingestMetrics(pubId);
      await load();
      onIngestSuccess?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setIngesting(false);
    }
  };

  if (loading && !detail) {
    return <div className="card h-40 animate-pulse" aria-hidden="true" />;
  }
  if (error && !detail) {
    return (
      <Alert tone="danger" title="Metrik tidak bisa dimuat">
        {error}
        <div className="mt-2"><Button size="xs" variant="secondary" onClick={load}>Coba lagi</Button></div>
      </Alert>
    );
  }
  if (!detail) return null;

  const metrics = detail.metrics || {};
  const available = detail.available_metrics || {};

  return (
    <Card>
      <CardHeader
        title={truncate(detail.topic || `Publikasi #${detail.publication_id}`, 80)}
        description={`Instagram media ID ${detail.media_id} · ${detail.format}`}
        icon={InstagramIcon}
        actions={
          <>
            <Button size="xs" variant="secondary" icon={RefreshCw} loading={ingesting} onClick={ingest}>
              Ambil metrik terbaru
            </Button>
            {detail.permalink && (
              <a href={detail.permalink} target="_blank" rel="noreferrer" className="btn btn-secondary btn-xs">
                <ExternalLink className="h-3 w-3" aria-hidden="true" /> Buka
              </a>
            )}
            <Button size="xs" variant="ghost" onClick={onClose}>Tutup</Button>
          </>
        }
      />

      <div className="space-y-4 p-5">
        {error && <Alert tone="warning" title="Pembaruan metrik gagal">{error}</Alert>}

        <div className="flex flex-wrap items-center gap-2 text-[11px] text-ink-muted">
          {detail.published_at && <span>Tayang {timeAgo(detail.published_at)}</span>}
          {metrics.collected_at && <span>· Data diambil {timeAgo(metrics.collected_at)}</span>}
          {metrics.source && <span>· Sumber {metrics.source}</span>}
          {metrics.is_simulated && <Badge tone="warning">data simulasi</Badge>}
          {isMissing(metrics.engagement_rate) ? (
            <Badge tone="neutral">engagement rate belum tersedia</Badge>
          ) : (
            <Badge tone="success">engagement rate {metrics.engagement_rate}%</Badge>
          )}
        </div>

        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {METRIC_FIELDS.map((field) => (
            <MetricTile
              key={field.key}
              label={field.label}
              icon={field.icon}
              value={metrics[field.key]}
              available={Boolean(available[field.key])}
            />
          ))}
        </dl>

        {Object.values(available).every((v) => !v) && (
          <Alert tone="info" title="Metrik belum tersedia">
            Instagram belum mengembalikan angka untuk postingan ini. Tekan
            {' '}<strong>Ambil metrik terbaru</strong>{' '}setelah postingan tayang beberapa saat —
            nilai yang tidak didukung API akan tetap kosong, bukan nol.
          </Alert>
        )}

        {(detail.history || []).length > 0 && (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Riwayat pengambilan ({detail.history.length})
            </p>
            <ul className="max-h-48 divide-y divide-line overflow-y-auto rounded-xl border border-line">
              {[...detail.history].reverse().map((snap, index) => (
                <li key={`${snap.collected_at}-${index}`} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs">
                  <span className="text-ink-muted">{timeAgo(snap.collected_at)}</span>
                  <span className="flex flex-wrap gap-2 text-ink">
                    <span>Reach {isMissing(snap.reach) ? '—' : fmtNumber(snap.reach)}</span>
                    <span>Views {isMissing(snap.views) ? '—' : fmtNumber(snap.views)}</span>
                    <span>Likes {isMissing(snap.likes) ? '—' : fmtNumber(snap.likes)}</span>
                    <span>Saves {isMissing(snap.saves) ? '—' : fmtNumber(snap.saves)}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {(detail.comparison || []).length > 0 && (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
              Dibandingkan konten lain
            </p>
            <ul className="divide-y divide-line rounded-xl border border-line">
              {detail.comparison.slice(0, 6).map((peer) => (
                <li key={peer.publication_id} className="flex items-center justify-between gap-2 px-3 py-2 text-xs">
                  <span className="min-w-0 truncate text-ink">{peer.topic || `#${peer.publication_id}`}</span>
                  <span className="shrink-0 text-ink-muted">
                    Reach {isMissing(peer.reach) ? '—' : fmtNumber(peer.reach)} ·
                    {' '}Likes {isMissing(peer.likes) ? '—' : fmtNumber(peer.likes)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}

export default function PublicationAnalytics({ onIngestSuccess }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [ingestingAll, setIngestingAll] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getAnalyticsPublications();
      setItems(res.items || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const ingestAll = async () => {
    setIngestingAll(true);
    try {
      await api.ingestMetrics(null);
      await load();
      onIngestSuccess?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setIngestingAll(false);
    }
  };

  const totals = useMemo(() => {
    const withReach = items.filter((i) => !isMissing(i.reach));
    return {
      tracked: items.length,
      withData: withReach.length,
      reach: withReach.length
        ? withReach.reduce((sum, i) => sum + (i.reach || 0), 0)
        : null,
    };
  }, [items]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Performa per postingan Instagram</h2>
          <p className="mt-0.5 text-xs text-ink-muted">
            Diambil langsung dari Instagram Graph API memakai media ID asli setiap postingan.
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" icon={RefreshCw} onClick={load} loading={loading}>
            Muat ulang
          </Button>
          <Button size="sm" icon={InstagramIcon} onClick={ingestAll} loading={ingestingAll} disabled={!items.length}>
            Ambil semua metrik
          </Button>
        </div>
      </div>

      {error && !items.length && (
        <Alert tone="danger" title="Daftar konten tidak bisa dimuat">{error}</Alert>
      )}

      {items.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatCard label="Postingan terhubung" value={fmtNumber(totals.tracked)} helper="Punya media ID Instagram" icon={InstagramIcon} tone="brand" />
          <StatCard label="Sudah ada metrik" value={fmtNumber(totals.withData)} helper="Sisanya menunggu pengambilan data" icon={Eye} tone="success" />
          <StatCard label="Total reach" value={isMissing(totals.reach) ? '—' : fmtNumber(totals.reach)} helper="Hanya dari konten yang metriknya tersedia" icon={TrendingUp} />
        </div>
      )}

      {selected && <PublicationDetail pubId={selected} onClose={() => setSelected(null)} onIngestSuccess={onIngestSuccess} />}

      <Card>
        <CardHeader
          title="Daftar konten tayang"
          description="Klik satu konten untuk melihat Reach, Impressions, Likes, Comments, Shares, Saves, Views, dan engagement rate."
          icon={InstagramIcon}
        />
        {loading && !items.length ? (
          <div className="space-y-2 p-5">
            {[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-xl bg-canvas" aria-hidden="true" />)}
          </div>
        ) : items.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={AlertTriangle}
              title="Belum ada konten yang tayang lewat aplikasi ini"
              description="Metrik per postingan hanya dapat ditampilkan untuk konten yang dipublikasikan dari GTNIC, karena media ID Instagram dicatat saat publikasi."
              className="border-0 bg-transparent"
            />
          </div>
        ) : (
          <ul className="divide-y divide-line">
            {items.map((item) => {
              const metrics = item.metrics || {};
              const metricCount = METRIC_FIELDS.filter((f) => !isMissing(metrics[f.key])).length;
              return (
                <li key={item.publication_id}>
                  <button
                    type="button"
                    onClick={() => setSelected(item.publication_id)}
                    className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-canvas/70"
                  >
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                      <InstagramIcon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-ink">
                        {truncate(item.topic || `Publikasi #${item.publication_id}`, 80)}
                      </span>
                      <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-subtle">
                        <span className="uppercase">{item.format}</span>
                        {item.published_at && <span>· {timeAgo(item.published_at)}</span>}
                        <span>· media ID {item.media_id}</span>
                        {metricCount === 0 && <Badge tone="neutral">metrik belum diambil</Badge>}
                      </span>
                    </span>
                    <span className="hidden shrink-0 items-center gap-3 text-xs text-ink-muted sm:flex">
                      <span>Reach {isMissing(metrics.reach) ? '—' : fmtNumber(metrics.reach)}</span>
                      <span>Likes {isMissing(metrics.likes) ? '—' : fmtNumber(metrics.likes)}</span>
                    </span>
                    <ChevronRight className="h-4 w-4 shrink-0 text-ink-subtle" aria-hidden="true" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
