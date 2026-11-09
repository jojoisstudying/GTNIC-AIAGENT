import { useMemo, useState } from 'react';
import {
  CalendarDays,
  Check,
  ChevronDown,
  Film,
  Layers,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react';
import { Badge, Button, Card, EmptyState, PageHeader, Pills, StatusBadge } from '../components/ui';
import { fmtDayName, strategyStatusMeta } from '../lib/format';
import { cn } from '../lib/utils';

const FILTERS = [
  { key: 'all', label: 'Semua' },
  { key: 'action', label: 'Perlu keputusan' },
  { key: 'approved', label: 'Siap dibuat' },
  { key: 'published', label: 'Sudah tayang' },
];

const NEEDS_ACTION = new Set(['draft', 'awaiting_approval']);
const READY = new Set(['approved', 'approved_to_publish']);
const PUBLISHED = new Set(['published', 'scheduled', 'publishing']);

export default function Strategy({ items = [], loading, onRegenerate, onStatusChange, onGenerate, regenerating, isGenerating = false }) {
  const [filter, setFilter] = useState('all');
  const [expanded, setExpanded] = useState({});
  const [busy, setBusy] = useState(null);

  const counts = useMemo(
    () => ({
      all: items.length,
      action: items.filter((item) => NEEDS_ACTION.has(item.status)).length,
      approved: items.filter((item) => READY.has(item.status)).length,
      published: items.filter((item) => PUBLISHED.has(item.status)).length,
    }),
    [items]
  );

  const filtered = useMemo(() => {
    const list = items.filter((item) => {
      if (filter === 'action') return NEEDS_ACTION.has(item.status);
      if (filter === 'approved') return READY.has(item.status);
      if (filter === 'published') return PUBLISHED.has(item.status);
      return true;
    });
    return [...list].sort((a, b) => {
      const byDate = String(a.plan_date).localeCompare(String(b.plan_date));
      if (byDate !== 0) return byDate;
      return String(a.scheduled_slot || '').localeCompare(String(b.scheduled_slot || ''));
    });
  }, [items, filter]);

  const grouped = useMemo(() => {
    const map = new Map();
    filtered.forEach((item) => {
      const key = item.plan_date || 'Tanpa tanggal';
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(item);
    });
    return [...map.entries()];
  }, [filtered]);

  const handleStatus = async (item, status) => {
    setBusy(item.id);
    try {
      await onStatusChange(item.id, status);
    } finally {
      setBusy(null);
    }
  };

  const handleGenerate = async (item) => {
    setBusy(item.id);
    try {
      await onGenerate(item.id);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Kalender strategi konten"
        description="Rencana konten 7 hari yang disusun AI dari profil enterprise Anda. Setujui item yang sesuai agar bisa langsung dibuat."
        actions={
          <Button
            variant="secondary"
            size="sm"
            icon={RefreshCw}
            loading={regenerating}
            onClick={onRegenerate}
          >
            Susun ulang kalender
          </Button>
        }
      />

      <Pills
        ariaLabel="Filter kalender"
        value={filter}
        onChange={setFilter}
        items={FILTERS.map((item) => ({ ...item, count: counts[item.key] }))}
      />

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="card h-28 animate-pulse" aria-hidden="true" />
          ))}
        </div>
      ) : grouped.length === 0 ? (
        <EmptyState
          icon={CalendarDays}
          title={items.length === 0 ? 'Kalender belum tersedia' : 'Tidak ada item pada filter ini'}
          description={
            items.length === 0
              ? 'Kalender akan dibuat otomatis dari profil enterprise Anda. Jika belum muncul, coba susun ulang.'
              : 'Pilih filter lain untuk melihat item lainnya.'
          }
          action={
            items.length === 0 ? (
              <Button size="sm" icon={RefreshCw} loading={regenerating} onClick={onRegenerate}>
                Buat kalender
              </Button>
            ) : (
              <Button size="sm" variant="secondary" onClick={() => setFilter('all')}>
                Lihat semua
              </Button>
            )
          }
        />
      ) : (
        <div className="space-y-6">
          {grouped.map(([date, dayItems]) => (
            <section key={date}>
              <div className="mb-2 flex items-center gap-2">
                <h2 className="text-sm font-semibold text-ink">
                  {fmtDayName(date) ? `${fmtDayName(date)}, ` : ''}
                  {date}
                </h2>
                <span className="text-xs text-ink-muted">{dayItems.length} item</span>
              </div>

              <ul className="space-y-2.5">
                {dayItems.map((item) => {
                  const meta = strategyStatusMeta(item.status);
                  const isOpen = Boolean(expanded[item.id]);
                  const itemBusy = busy === item.id;
                  return (
                    <li key={item.id} className="card p-4">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Badge tone="neutral" className="bg-canvas">
                              {item.scheduled_slot || 'Tanpa jam'}
                            </Badge>
                            <Badge tone={item.format === 'video' ? 'brand' : 'neutral'} className={item.format === 'video' ? '' : 'bg-canvas'}>
                              {item.format === 'video' ? (
                                <><Film className="h-3 w-3" aria-hidden="true" /> Reels</>
                              ) : (
                                <><Layers className="h-3 w-3" aria-hidden="true" /> Carousel</>
                              )}
                            </Badge>
                            {item.content_pillar && <Badge tone="neutral">{item.content_pillar}</Badge>}
                            <StatusBadge meta={meta} dot />
                          </div>

                          <h3 className="mt-2 text-sm font-semibold leading-snug text-ink">{item.topic}</h3>
                          <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                            {item.objective && <><strong className="font-medium text-ink">Tujuan:</strong> {item.objective}</>}
                            {item.objective && item.target_segment && <span className="mx-1.5 text-ink-subtle">·</span>}
                            {item.target_segment && <><strong className="font-medium text-ink">Target:</strong> {item.target_segment}</>}
                          </p>

                          {item.rationale && (
                            <>
                              <button
                                type="button"
                                onClick={() => setExpanded((prev) => ({ ...prev, [item.id]: !prev[item.id] }))}
                                aria-expanded={isOpen}
                                className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-brand-700 hover:underline"
                              >
                                <ChevronDown className={cn('h-3 w-3 transition-transform', isOpen && 'rotate-180')} aria-hidden="true" />
                                {isOpen ? 'Sembunyikan alasan' : 'Kenapa topik ini?'}
                              </button>
                              {isOpen && <p className="mt-1 text-xs italic leading-relaxed text-ink-muted">{item.rationale}</p>}
                            </>
                          )}

                          {item.last_error && (
                            <p className="mt-1.5 text-[11px] leading-snug text-danger-600">{item.last_error}</p>
                          )}
                        </div>

                        <div className="flex shrink-0 flex-wrap items-center gap-1.5 lg:pl-4">
                          {item.status === 'draft' && (
                            <>
                              <Button
                                size="sm"
                                variant="success"
                                icon={Check}
                                loading={itemBusy}
                                onClick={() => handleStatus(item, 'approved')}
                              >
                                Setujui
                              </Button>
                              <Button
                                size="sm"
                                variant="secondary"
                                icon={X}
                                disabled={itemBusy}
                                onClick={() => handleStatus(item, 'rejected')}
                              >
                                Tolak
                              </Button>
                            </>
                          )}

                          {item.status === 'awaiting_approval' && (
                            <>
                              <Button
                                size="sm"
                                variant="success"
                                icon={Check}
                                loading={itemBusy}
                                onClick={() => handleStatus(item, 'approved')}
                              >
                                Setujui
                              </Button>
                              <Button
                                size="sm"
                                variant="secondary"
                                icon={X}
                                disabled={itemBusy}
                                onClick={() => handleStatus(item, 'rejected')}
                              >
                                Tolak
                              </Button>
                            </>
                          )}

                          {READY.has(item.status) && (
                            <Button
                              size="sm"
                              icon={Sparkles}
                              loading={itemBusy}
                              disabled={isGenerating || itemBusy}
                              title={isGenerating ? 'AI sedang memproses generasi lain' : undefined}
                              onClick={() => handleGenerate(item)}
                            >
                              Buat konten ini
                            </Button>
                          )}

                          {item.status === 'generation_failed' && (
                            <Button
                              size="sm"
                              variant="secondary"
                              icon={Sparkles}
                              loading={itemBusy}
                              onClick={() => handleStatus(item, 'approved')}
                            >
                              Coba lagi
                            </Button>
                          )}

                          {item.status === 'rejected' && (

                            <Button size="sm" variant="secondary" icon={RefreshCw} loading={itemBusy} onClick={() => handleStatus(item, 'draft')}>

                              Pulihkan ke draf

                            </Button>

                          )}


                          {!NEEDS_ACTION.has(item.status) && !READY.has(item.status) && item.status !== 'generation_failed' && item.status !== 'rejected' && (
                            <span className="text-xs text-ink-subtle">Tidak ada aksi tersedia</span>
                          )}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}

      <Card className="p-4">
        <p className="text-xs leading-relaxed text-ink-muted">
          <strong className="text-ink">Catatan:</strong> kalender hanya mengusulkan tanggal dan jam tayang. Posting
          otomatis hanya berjalan bila penjadwal di backend diaktifkan. Item yang ditolak tidak akan dibuat.
        </p>
      </Card>
    </div>
  );
}
