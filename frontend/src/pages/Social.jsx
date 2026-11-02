import { useCallback, useEffect, useState } from 'react';
import {
  Clock,
  ExternalLink,
  Link2,
  RefreshCw,
  Send,
  Settings2,
  ShieldAlert,
  Timer,
} from 'lucide-react';
import { api } from '../api';
import { FacebookIcon as Facebook, InstagramIcon as Instagram } from '../components/BrandIcons';
import { Alert, Badge, Button, Card, CardHeader, EmptyState, PageHeader, Spinner, StatusBadge } from '../components/ui';
import { fmtTime, publicationMeta, timeAgo } from '../lib/format';
import { cn } from '../lib/utils';

function ConnectionCard({ icon: Icon, title, status, ok, description, children }) {
  return (
    <Card className="flex flex-col p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className={cn('flex h-10 w-10 items-center justify-center rounded-xl', ok ? 'bg-success-50 text-success-600' : 'bg-canvas text-ink-muted')}>
            <Icon className="h-5 w-5" aria-hidden="true" />
          </span>
          <div>
            <p className="text-sm font-semibold text-ink">{title}</p>
            <p className={cn('text-xs font-medium', ok ? 'text-success-700' : 'text-ink-muted')}>{status}</p>
          </div>
        </div>
        <span className={cn('mt-1 h-2.5 w-2.5 rounded-full', ok ? 'bg-success-500' : 'bg-ink-subtle')} aria-hidden="true" />
      </div>
      <p className="mt-3 text-xs leading-relaxed text-ink-muted">{description}</p>
      {children && <div className="mt-3">{children}</div>}
    </Card>
  );
}

export default function Social({ brand, apiKeySet, onNavigateSettings }) {
  const [ops, setOps] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOps(await api.getOpsStatus());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const scheduler = ops?.scheduler;
  const ingestion = ops?.analytics_ingestion;
  const publications = ops?.recent_publications || [];
  const calendarByStatus = ops?.calendar_by_status || {};
  const pendingApprovals = ops?.pending_approvals || [];
  const failed = ops?.failed_workflows || [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Koneksi sosial & publikasi"
        description="Status integrasi yang benar-benar tersedia di aplikasi ini, tanpa klaim fitur yang belum ada."
        actions={
          <Button variant="secondary" size="sm" icon={RefreshCw} onClick={load} loading={loading}>
            Periksa ulang
          </Button>
        }
      />

      {loading && !ops ? (
        <div className="card p-10">
          <Spinner label="Memeriksa status integrasi…" />
        </div>
      ) : error ? (
        <EmptyState
          icon={ShieldAlert}
          title="Status integrasi tidak bisa dimuat"
          description={error}
          action={<Button icon={RefreshCw} onClick={load}>Coba lagi</Button>}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <ConnectionCard
              icon={Instagram}
              title="Instagram"
              status={ingestion?.instagram_configured ? 'Terhubung untuk publikasi' : 'Belum terkonfigurasi'}
              ok={Boolean(ingestion?.instagram_configured)}
              description={
                ingestion?.instagram_configured
                  ? `Akun Instagram aktif. Publikasi dijalankan dari halaman konten. Metrik terakhir masuk: ${
                      ingestion?.last_real_metrics_at ? timeAgo(ingestion.last_real_metrics_at) : 'belum ada'
                    }.`
                  : 'Publikasi ke Instagram membutuhkan kredensial di sisi server (IG_USER_ID, IG_TOKEN, dan Cloudinary). Selama belum diisi, tombol posting akan gagal dengan pesan dari server.'
              }
            >
              {!ingestion?.instagram_configured && (
                <div className="rounded-xl bg-canvas p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-muted">Yang perlu diisi di server</p>
                  <ul className="mt-1 space-y-0.5 font-mono text-[11px] text-ink-muted">
                    <li>IG_USER_ID</li>
                    <li>IG_TOKEN</li>
                    <li>CLOUDINARY_CLOUD_NAME / API_KEY / API_SECRET</li>
                  </ul>
                  <p className="mt-1.5 text-[11px] leading-relaxed text-ink-subtle">
                    Kredensial tidak dapat diisi dari antarmuka ini karena bersifat rahasia server.
                  </p>
                </div>
              )}
            </ConnectionCard>

            <ConnectionCard
              icon={Timer}
              title="Penjadwal otomatis"
              status={scheduler?.enabled ? (scheduler?.active ? 'Aktif dan berjalan' : 'Aktif, menunggu giliran') : 'Nonaktif'}
              ok={Boolean(scheduler?.enabled)}
              description={
                scheduler?.enabled
                  ? 'Konten pada kalender berstatus “terjadwal” akan diposting otomatis sesuai jadwal oleh backend.'
                  : 'Saat ini konten hanya diposting manual dari halaman konten. Penjadwal diaktifkan lewat konfigurasi SCHEDULER_ENABLED di server.'
              }
            >
              {scheduler?.lease_expires_at && (
                <p className="text-[11px] text-ink-muted">Sewa penjadwal berlaku sampai {fmtTime(scheduler.lease_expires_at)}</p>
              )}
            </ConnectionCard>

            <ConnectionCard
              icon={Facebook}
              title="Facebook"
              status="Belum tersedia"
              ok={false}
              description="Backend aplikasi ini baru mengintegrasikan Instagram. Publikasi ke Facebook belum didukung, jadi tidak ada tombol yang bisa diklik untuk itu."
            />

            <ConnectionCard
              icon={Link2}
              title="Akses API dari browser"
              status={apiKeySet ? 'Kunci tersimpan' : 'Kunci belum diatur'}
              ok={apiKeySet}
              description={
                apiKeySet
                  ? 'Permintaan yang mengubah data (buat konten, setujui, posting) dikirim dengan kunci API dari browser ini.'
                  : 'Tanpa kunci API, permintaan yang mengubah data akan ditolak server. Atur kuncinya di halaman Pengaturan.'
              }
            >
              {!apiKeySet && (
                <Button size="xs" variant="secondary" icon={Settings2} onClick={onNavigateSettings}>
                  Atur kunci API
                </Button>
              )}
            </ConnectionCard>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader
                title="Publikasi terakhir"
                description="10 percobaan publikasi terakhir yang dicatat backend."
                icon={Send}
              />
              {publications.length === 0 ? (
                <div className="p-5">
                  <EmptyState
                    icon={Instagram}
                    title="Belum ada publikasi"
                    description="Setelah Anda memposting konten, riwayatnya akan tampil di sini beserta tautannya."
                    className="border-0 bg-transparent"
                  />
                </div>
              ) : (
                <ul className="divide-y divide-line">
                  {publications.map((publication, index) => {
                    const meta = publicationMeta(publication.status);
                    return (
                      <li key={`${publication.run_id}-${index}`} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                        <div className="min-w-0">
                          <p className="truncate font-mono text-xs text-ink">{publication.run_id}</p>
                          {publication.error && (
                            <p className="mt-0.5 line-clamp-2 text-[11px] text-danger-600">{publication.error}</p>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <StatusBadge meta={meta} dot />
                          {publication.permalink && (
                            <a
                              href={publication.permalink}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline"
                            >
                              Buka <ExternalLink className="h-3 w-3" aria-hidden="true" />
                            </a>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>

            <Card>
              <CardHeader title="Antrian kalender" icon={Clock} />
              <div className="space-y-2 p-4 text-sm">
                {Object.keys(calendarByStatus).length === 0 ? (
                  <p className="text-xs text-ink-muted">Belum ada item kalender.</p>
                ) : (
                  Object.entries(calendarByStatus).map(([status, count]) => (
                    <div key={status} className="flex items-center justify-between">
                      <span className="capitalize text-ink-muted">{status.replace(/_/g, ' ')}</span>
                      <Badge tone="neutral" className="bg-canvas">{count}</Badge>
                    </div>
                  ))
                )}
                {pendingApprovals.length > 0 && (
                  <p className="pt-2 text-xs leading-relaxed text-warning-700">
                    {pendingApprovals.length} item menunggu persetujuan Anda.
                  </p>
                )}
                {failed.length > 0 && (
                  <p className="text-xs leading-relaxed text-danger-600">
                    {failed.length} alur gagal dan perlu ditinjau.
                  </p>
                )}
              </div>
            </Card>
          </div>

          <Alert tone="info" title="Apa yang bisa dan tidak bisa dilakukan dari halaman ini">
            <ul className="mt-1 list-disc space-y-1 pl-4">
              <li>Posting ke Instagram dilakukan dari halaman konten setelah Anda menyetujui hasilnya.</li>
              <li>Koneksi akun dan penjadwal diatur lewat konfigurasi server, bukan dari tombol di antarmuka.</li>
              <li>Jika Instagram belum terkonfigurasi, {brand?.company ? `${brand.company} ` : ''}tetap bisa membuat konten dan menyimpannya, hanya posting yang belum bisa dijalankan.</li>
            </ul>
          </Alert>
        </>
      )}
    </div>
  );
}
