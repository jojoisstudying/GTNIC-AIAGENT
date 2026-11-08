import { Check, Image as ImageIcon, RefreshCw, Upload } from 'lucide-react';
import { Badge, Button, Card, EmptyState, PageHeader, Pills, StatusBadge } from '../components/ui';
import { assetStatusMeta, fmtTime } from '../lib/format';
import { cn } from '../lib/utils';
import { mediaUrl } from '../api';

const FILTERS = [
  { key: 'all', label: 'Semua' },
  { key: 'pending_review', label: 'Menunggu review' },
  { key: 'approved', label: 'Disetujui' },
  { key: 'rejected', label: 'Ditolak' },
];

export default function Assets({
  assets,
  assetCounts,
  assetFilter,
  onChangeFilter,
  approvingAssetId,
  regeneratingId,
  onApprove,
  onRegenerate,
  onOpenRun,
  onNavigateBrand,
  loading,
}) {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Asset library"
        description="Pose dan foto yang dibuat AI untuk konten Anda. Setujui pose agar bisa dipakai pada slide final."
        actions={
          <Button size="sm" icon={Upload} onClick={onNavigateBrand}>
            Unggah foto model
          </Button>
        }
      />

      <Pills
        ariaLabel="Filter status aset"
        value={assetFilter}
        onChange={onChangeFilter}
        items={FILTERS.map((filter) => ({
          ...filter,
          count: assetCounts[filter.key] ?? 0,
          highlight: filter.key === 'pending_review',
        }))}
      />

      {loading && assets.length === 0 ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="card h-56 animate-pulse" aria-hidden="true" />
          ))}
        </div>
      ) : assets.length === 0 ? (
        <EmptyState
          icon={ImageIcon}
          title={
            assetFilter === 'pending_review'
              ? 'Tidak ada pose yang menunggu review'
              : 'Belum ada aset pada filter ini'
          }
          description={
            assetFilter === 'all'
              ? 'Pose akan muncul otomatis saat AI membuat konten yang membutuhkan foto model.'
              : 'Coba filter lain, atau unggah foto model agar AI bisa membuat variasi pose.'
          }
          action={
            <Button size="sm" variant="secondary" icon={Upload} onClick={onNavigateBrand}>
              Buka Brand & Aset
            </Button>
          }
        />
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {assets.map((asset) => {
            const meta = assetStatusMeta(asset.status);
            return (
              <li key={asset.id} className="card flex flex-col overflow-hidden">
                <div className="relative aspect-square bg-canvas">
                  {asset.url ? (
                    <img
                      src={mediaUrl(asset.url)}
                      alt={asset.description || `Aset ${asset.id}`}
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center">
                      <ImageIcon className="h-8 w-8 text-ink-subtle" aria-hidden="true" />
                    </div>
                  )}
                  <span className="absolute left-2 top-2">
                    <StatusBadge meta={meta} dot />
                  </span>
                </div>

                <div className="flex flex-1 flex-col gap-2 p-3">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-ink">{asset.description || `Aset ${asset.id}`}</p>
                    {asset.created_at && (
                      <p className="mt-0.5 text-[11px] text-ink-subtle">{fmtTime(asset.created_at)}</p>
                    )}
                  </div>

                  {asset.tags?.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {asset.tags.slice(0, 3).map((tag, index) => (
                        <span key={index} className={cn('rounded bg-canvas px-1.5 py-0.5 text-[10px] text-ink-muted')}>
                          #{tag}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="mt-auto space-y-1.5">
                    {asset.status === 'pending_review' && (
                      <div className="flex gap-1.5">
                        <Button
                          size="xs"
                          variant="success"
                          icon={Check}
                          className="flex-1"
                          loading={approvingAssetId === asset.id}
                          disabled={Boolean(approvingAssetId) || Boolean(regeneratingId)}
                          onClick={() => onApprove(asset.id, 'approved', asset.run_id)}
                        >
                          Setujui
                        </Button>
                        <Button
                          size="xs"
                          variant="secondary"
                          className="flex-1"
                          disabled={Boolean(approvingAssetId) || Boolean(regeneratingId)}
                          onClick={() => onApprove(asset.id, 'rejected', asset.run_id)}
                        >
                          Tolak
                        </Button>
                      </div>
                    )}

                    {asset.status === 'rejected' && asset.person_id && (
                      <Button
                        size="xs"
                        variant="secondary"
                        icon={RefreshCw}
                        className="w-full"
                        loading={regeneratingId === asset.id}
                        onClick={() => onRegenerate(asset.id, asset.run_id)}
                      >
                        Buat ulang pose
                      </Button>
                    )}

                    {asset.run_id && (
                      <button
                        type="button"
                        onClick={() => onOpenRun(asset.run_id)}
                        className="block w-full text-left text-[11px] font-semibold text-brand-700 hover:underline"
                      >
                        Buka konten terkait →
                      </button>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <Badge tone="neutral" className="bg-canvas">Total aset</Badge>
          <span>{assetCounts.all ?? assets.length}</span>
          <span className="text-ink-subtle">·</span>
          <Badge tone="warning">{assetCounts.pending_review ?? 0} menunggu review</Badge>
          <Badge tone="success">{assetCounts.approved ?? 0} disetujui</Badge>
          <Badge tone="danger">{assetCounts.rejected ?? 0} ditolak</Badge>
        </div>
      </Card>
    </div>
  );
}
