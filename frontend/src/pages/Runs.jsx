import { AlertCircle, Clock, Film, Image as ImageIcon, Layers, Play, RefreshCw } from 'lucide-react';
import { Badge, Button, Card, EmptyState, PageHeader, Pills, StatusBadge } from '../components/ui';
import { fmtMoney, fmtTime, runStatusMeta } from '../lib/format';
import { cn } from '../lib/utils';

const FILTERS = [
  { key: 'all', label: 'Semua' },
  { key: 'awaiting_approval', label: 'Menunggu persetujuan' },
  { key: 'running', label: 'Sedang diproses' },
  { key: 'ok', label: 'Selesai' },
  { key: 'failed', label: 'Gagal' },
];

export default function Runs({ runs, runsFilter, setRunsFilter, pendingRunsCount, onRefresh, onOpenRun, currentRunId, loading }) {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Riwayat konten"
        description="Buka konten lama untuk melihat hasil, melanjutkan proses yang tertunda, atau memposting ulang bila diizinkan."
        actions={
          <Button variant="secondary" size="sm" icon={RefreshCw} onClick={onRefresh} loading={loading}>
            Muat ulang
          </Button>
        }
      />

      <Pills
        ariaLabel="Filter status konten"
        value={runsFilter}
        onChange={setRunsFilter}
        items={FILTERS.map((filter) => ({
          ...filter,
          count: filter.key === 'awaiting_approval' ? pendingRunsCount : undefined,
          highlight: filter.key === 'awaiting_approval',
        }))}
      />

      {loading && runs.length === 0 ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="card h-28 animate-pulse" aria-hidden="true" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <EmptyState
          icon={Clock}
          title={
            runsFilter === 'awaiting_approval'
              ? 'Tidak ada konten yang menunggu persetujuan'
              : runsFilter === 'failed'
                ? 'Tidak ada konten yang gagal'
                : 'Belum ada konten'
          }
          description={
            runsFilter === 'all'
              ? 'Konten yang Anda buat akan muncul di sini lengkap dengan statusnya.'
              : 'Coba pilih filter lain untuk melihat konten yang tersedia.'
          }
          action={
            runsFilter === 'all' ? (
              <Button size="sm" onClick={() => setRunsFilter('all')}>Muat daftar</Button>
            ) : (
              <Button size="sm" variant="secondary" onClick={() => setRunsFilter('all')}>Lihat semua</Button>
            )
          }
        />
      ) : (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {runs.map((run) => {
            const meta = runStatusMeta(run.status);
            const active = run.run_id === currentRunId;
            return (
              <li key={run.run_id}>
                <button
                  type="button"
                  onClick={() => onOpenRun(run.run_id, run.format, run.status)}
                  className={cn(
                    'card card-hover flex h-full w-full items-start gap-3 p-3 text-left',
                    active && 'border-brand-400 ring-2 ring-brand-400/20'
                  )}
                >
                  <span className="flex h-20 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-line bg-canvas">
                    {run.thumbnail_url ? (
                      <img src={run.thumbnail_url} alt="" className="h-full w-full object-cover" loading="lazy" />
                    ) : run.format === 'video' ? (
                      <Play className="h-6 w-6 text-brand-500" aria-hidden="true" />
                    ) : (
                      <ImageIcon className="h-6 w-6 text-ink-subtle" aria-hidden="true" />
                    )}
                  </span>

                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-2 text-sm font-semibold leading-snug text-ink">{run.topic}</span>
                    <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <StatusBadge meta={meta} dot />
                      <Badge tone="neutral" className="bg-canvas">
                        {run.format === 'video' ? (
                          <><Film className="h-3 w-3" aria-hidden="true" /> Reels</>
                        ) : (
                          <><Layers className="h-3 w-3" aria-hidden="true" /> Carousel</>
                        )}
                      </Badge>
                      {run.pending_review_count > 0 && (
                        <Badge tone="warning">{run.pending_review_count} pose menunggu</Badge>
                      )}
                    </span>
                    <span className="mt-1.5 block text-[11px] text-ink-subtle">
                      {fmtTime(run.started_at)} · {fmtMoney(run.cost_usd)}
                    </span>
                    {run.status === 'failed' && run.error && (
                      <span className="mt-1 flex items-start gap-1 text-[11px] leading-snug text-danger-600">
                        <AlertCircle className="mt-px h-3 w-3 shrink-0" aria-hidden="true" />
                        <span className="line-clamp-2">{run.error}</span>
                      </span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <Card className="p-4">
        <p className="text-xs leading-relaxed text-ink-muted">
          <strong className="text-ink">Catatan:</strong> konten berstatus “Menunggu persetujuan” berhenti sampai Anda
          menyetujui pose foto di halaman detail konten. Konten yang sudah diposting tidak dapat diposting ulang
          dari aplikasi.
        </p>
      </Card>
    </div>
  );
}
