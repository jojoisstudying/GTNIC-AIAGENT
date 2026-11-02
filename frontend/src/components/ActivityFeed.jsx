import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ListChecks, Loader2, Terminal } from 'lucide-react';
import { Segmented } from './ui';
import { cn } from '../lib/utils';
import { eventKindMeta, fmtTime, stepLabel, summarizeEvent, truncate } from '../lib/format';

export default function ActivityFeed({ events = [], isRunning = false, status }) {
  const [mode, setMode] = useState('ringkas');
  const [expanded, setExpanded] = useState({});
  const endRef = useRef(null);

  const steps = useMemo(() => {
    const seen = new Map();
    events.forEach((event) => {
      const key = event.step || 'pipeline';
      const current = seen.get(key) || { step: key, count: 0, last: null, errors: 0 };
      current.count += 1;
      current.last = event;
      if (event.kind === 'error' || event.status === 'error') current.errors += 1;
      seen.set(key, current);
    });
    return [...seen.values()];
  }, [events]);

  const visibleEvents = useMemo(() => {
    if (mode === 'detail') return events;
    return events.filter((event) => event.kind !== 'tool' || event.status === 'error' || Boolean(summarizeEvent(event)));
  }, [events, mode]);

  useEffect(() => {
    if (mode !== 'detail') return;
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [events, mode]);

  return (
    <div className="card flex min-h-[26rem] flex-col overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-brand-600" aria-hidden="true" />
          <p className="text-sm font-semibold text-ink">Proses AI</p>
          {isRunning && <Loader2 className="h-3.5 w-3.5 animate-spin text-brand-500" aria-label="Sedang berjalan" />}
        </div>
        <Segmented
          ariaLabel="Tampilan proses"
          value={mode}
          onChange={setMode}
          options={[
            { value: 'ringkas', label: 'Ringkas' },
            { value: 'detail', label: 'Detail teknis' },
          ]}
        />
      </div>

      {/* Ringkasan tahapan */}
      <div className="border-b border-line bg-canvas px-4 py-3">
        {steps.length === 0 ? (
          <p className="text-xs text-ink-muted">Tahapan akan muncul setelah AI mulai bekerja.</p>
        ) : (
          <ol className="flex flex-wrap gap-1.5">
            {steps.map((step) => (
              <li key={step.step}>
                <span
                  className={cn(
                    'inline-flex items-center gap-1 rounded-full border px-2 py-1 text-[11px] font-medium',
                    step.errors > 0
                      ? 'border-danger-100 bg-danger-50 text-danger-700'
                      : 'border-line bg-surface text-ink-muted'
                  )}
                  title={step.last ? `${step.count} catatan` : undefined}
                >
                  <span
                    className={cn('h-1.5 w-1.5 rounded-full', step.errors > 0 ? 'bg-danger-500' : 'bg-brand-400')}
                    aria-hidden="true"
                  />
                  {stepLabel(step.step)}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>

      {/* Daftar aktivitas */}
      <div className="max-h-[26rem] flex-1 overflow-y-auto p-3">
        {visibleEvents.length === 0 ? (
          <div className="flex h-full min-h-[12rem] flex-col items-center justify-center gap-2 text-center">
            <Terminal className="h-6 w-6 text-ink-subtle" aria-hidden="true" />
            <p className="text-sm text-ink-muted">
              {isRunning ? 'AI sedang menyiapkan langkah pertama…' : 'Belum ada aktivitas untuk konten ini.'}
            </p>
            {!isRunning && status && <p className="text-xs text-ink-subtle">Status: {status}</p>}
          </div>
        ) : (
          <ul className="space-y-2">
            {visibleEvents.map((event, index) => {
              const kind = eventKindMeta(event.kind);
              const summary = summarizeEvent(event);
              const isOpen = Boolean(expanded[event.id ?? index]);
              const detailIsObject = event.detail && typeof event.detail === 'object';
              return (
                <li
                  key={event.id ?? index}
                  className={cn(
                    'rounded-xl border px-3 py-2.5',
                    event.kind === 'error'
                      ? 'border-danger-100 bg-danger-50/60'
                      : 'border-line bg-surface'
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-1.5 text-xs font-semibold text-ink">
                        <span className="rounded-md bg-canvas px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ink-muted">
                          {stepLabel(event.step)}
                        </span>
                        <span className="truncate capitalize">{event.name || kind.label}</span>
                      </p>
                      {summary && (
                        <p className="mt-1 text-xs leading-relaxed text-ink-muted">{truncate(summary, mode === 'detail' ? 400 : 140)}</p>
                      )}
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-[10px] text-ink-subtle">{fmtTime(event.timestamp)}</p>
                      {event.duration_ms > 0 && (
                        <p className="text-[10px] text-ink-subtle">{(event.duration_ms / 1000).toFixed(1)} dtk</p>
                      )}
                    </div>
                  </div>

                  {detailIsObject && (
                    <>
                      <button
                        type="button"
                        onClick={() =>
                          setExpanded((prev) => ({ ...prev, [event.id ?? index]: !prev[event.id ?? index] }))
                        }
                        aria-expanded={isOpen}
                        className="mt-1.5 inline-flex items-center gap-1 text-[11px] font-semibold text-brand-700 hover:underline"
                      >
                        <ChevronDown className={cn('h-3 w-3 transition-transform', isOpen && 'rotate-180')} aria-hidden="true" />
                        {isOpen ? 'Sembunyikan detail' : 'Lihat detail teknis'}
                      </button>
                      {isOpen && (
                        <pre className="prose-raw mt-2 max-h-56 overflow-auto rounded-lg bg-canvas p-2.5 text-ink-muted">
                          {JSON.stringify(event.detail, null, 2)}
                        </pre>
                      )}
                    </>
                  )}
                </li>
              );
            })}
            <li ref={endRef} aria-hidden="true" />
          </ul>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-line bg-canvas px-4 py-2 text-[11px] text-ink-muted">
        <span>{events.length} catatan proses</span>
        <span className="hidden sm:inline">Setiap langkah AI tercatat dan bisa diaudit.</span>
      </div>
    </div>
  );
}
