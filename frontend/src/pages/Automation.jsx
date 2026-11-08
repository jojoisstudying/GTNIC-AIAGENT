import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Calendar,
  CalendarClock,
  CalendarPlus,
  CheckCircle2,
  Clock,
  ExternalLink,
  Eye,
  History,
  Loader2,
  Pause,
  Play,
  Power,
  RefreshCw,
  Settings2,
  Sparkles,
  Square,
  X,
} from 'lucide-react';
import { InstagramIcon as Instagram, FacebookIcon as Facebook } from '../components/BrandIcons';
import { api, mediaUrl } from '../api';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Modal,
  PageHeader,
  StatCard,
  StatusBadge,
  Switch,
} from '../components/ui';
import { automationStateMeta, fmtTime, timeAgo, truncate } from '../lib/format';
import { cn } from '../lib/utils';

const DAYS = [
  { value: 1, label: 'Sen' },
  { value: 2, label: 'Sel' },
  { value: 3, label: 'Rab' },
  { value: 4, label: 'Kam' },
  { value: 5, label: 'Jum' },
  { value: 6, label: 'Sab' },
  { value: 7, label: 'Min' },
];

const FORMATS = [
  { value: 'carousel', label: 'Carousel' },
  { value: 'single_image', label: 'Gambar tunggal' },
  { value: 'video', label: 'Video Reels' },
];

const STATUS_TONE = {
  success: 'text-success-600 bg-success-50',
  warning: 'text-warning-600 bg-warning-50',
  danger: 'text-danger-600 bg-danger-50',
  brand: 'text-brand-600 bg-brand-50',
  neutral: 'text-ink-muted bg-soft',
};

const WEEKDAY = { 1: 'Senin', 2: 'Selasa', 3: 'Rabu', 4: 'Kamis', 5: 'Jumat', 6: 'Sabtu', 7: 'Minggu' };

const STATUS_ICON = {
  needs_approval: Clock,
  draft: Clock,
  ready: Sparkles,
  scheduled: CalendarClock,
  publishing: Loader2,
  published: CheckCircle2,
  failed: AlertTriangle,
  cancelled: X,
  rejected: X,
};

const dayNameOf = (isoDate) => {
  if (!isoDate) return null;
  const date = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  const dow = date.getUTCDay();
  return WEEKDAY[dow === 0 ? 7 : dow];
};

const PIPELINE_STAGES = [
  { key: 'research', label: 'Riset' },
  { key: 'planner', label: 'Rencana' },
  { key: 'designer', label: 'Desain' },
  { key: 'video', label: 'Produksi' },
  { key: 'qc', label: 'QC' },
];

// Posisi tahap dari `step` nyata di event log — bukan persentase karangan.
const stageIndex = (step) => {
  const i = PIPELINE_STAGES.findIndex((s) => s.key === step);
  return i < 0 ? 0 : i;
};

/* ------------------------------------------------------------------ */
/* Baris jadwal minggu                                                 */
/* ------------------------------------------------------------------ */
function WeekRow({ row, busy, onApprove, onCancel, onPublish, onEditTopic, onReschedule, onPreview }) {
  const Icon = STATUS_ICON[row.status] || Clock;
  const tone = STATUS_TONE[row.status_tone] || STATUS_TONE.neutral;
  const day = dayNameOf(row.date);
  const fmtLabel = { reel: 'Reels', video: 'Reels', image: 'Gambar', carousel: 'Carousel' }[row.format] || row.format;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(row.topic || '');
  const canEditTopic = row.kind === 'calendar' && !['published', 'publishing'].includes(row.status);
  const canReschedule = !['published', 'publishing'].includes(row.status);
  const hasPreview = Boolean(row.run_id || row.publication_id);

  const submitTopic = () => {
    const next = draft.trim();
    if (!next || next === row.topic) {
      setEditing(false);
      return;
    }
    onEditTopic(row, next);
    setEditing(false);
  };

  return (
    <li className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <span className={cn('mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', tone)}>
          <Icon className={cn('h-4 w-4', row.status === 'publishing' && 'animate-spin')} aria-hidden="true" />
        </span>
        <div className="min-w-0 w-full">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-ink-muted">
            <span className="uppercase tracking-wide">
              {day || 'Tanpa tanggal'}{row.slot ? ` · ${row.slot}` : ''}
            </span>
            <Badge tone="neutral" className="bg-canvas text-[10px] uppercase">{fmtLabel}</Badge>
            <StatusBadge meta={{ label: row.status_label, tone: row.status_tone }} dot />
            {row.publish_attempts > 0 && (
              <span className="text-[10px] text-ink-subtle">percobaan {row.publish_attempts}</span>
            )}
          </div>
          {editing ? (
            <div className="mt-1 flex flex-col gap-1.5 sm:flex-row sm:items-center">
              <input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') submitTopic();
                  if (e.key === 'Escape') setEditing(false);
                }}
                className="input"
                aria-label="Topik konten baru"
              />
              <div className="flex gap-1.5">
                <Button size="xs" onClick={submitTopic} loading={busy === `topic-${row.ref_id}`}>Simpan</Button>
                <Button size="xs" variant="secondary" onClick={() => setEditing(false)}>Batal</Button>
              </div>
            </div>
          ) : (
            <p className="mt-0.5 text-sm font-semibold leading-snug text-ink">
              {truncate(row.topic || `Konten #${row.ref_id}`, 90)}
            </p>
          )}
          {row.error && (
            <p className="mt-1 line-clamp-2 break-words text-[11px] leading-relaxed text-danger-600">{row.error}</p>
          )}
          {row.permalink && (
            <a href={row.permalink} target="_blank" rel="noreferrer"
              className="mt-1 inline-block text-[11px] font-semibold text-brand-700 hover:underline">
              Lihat di Instagram →
            </a>
          )}
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-1.5 sm:justify-end">
        {hasPreview && (
          <Button size="xs" variant="secondary" icon={Eye} onClick={() => onPreview(row)}>
            Lihat hasil
          </Button>
        )}
        {row.can_approve && row.kind === 'calendar' && (
          <Button size="xs" icon={CheckCircle2} loading={busy === `approve-item-${row.ref_id}`}
            onClick={() => onApprove(row, 'item')}>
            Setujui
          </Button>
        )}
        {canEditTopic && !editing && (
          <Button size="xs" variant="secondary" onClick={() => { setDraft(row.topic || ''); setEditing(true); }}>
            Ubah topik
          </Button>
        )}
        {canReschedule && (
          <Button size="xs" variant="secondary" icon={Calendar} onClick={() => onReschedule(row)}>
            Ubah jadwal
          </Button>
        )}
        {row.can_approve && row.kind === 'publication' && (
          <Button size="xs" icon={CheckCircle2} loading={busy === `approve-pub-${row.ref_id}`}
            onClick={() => onApprove(row, 'publication')}>
            Setujui &amp; Jadwalkan
          </Button>
        )}
        {row.can_publish && row.publication_id && (
          <Button size="xs" variant="secondary" icon={Instagram}
            loading={busy === `publish-${row.publication_id}`}
            onClick={() => onPublish(row)}>
            Posting sekarang
          </Button>
        )}
        {row.can_cancel && row.publication_id && (
          <Button size="xs" variant="secondary" icon={X}
            loading={busy === `cancel-${row.publication_id}`}
            onClick={() => onCancel(row)}>
            Batalkan
          </Button>
        )}
      </div>
    </li>
  );
}

/* ------------------------------------------------------------------ */
/* Pengaturan minimalis (accordion)                                    */
/* ------------------------------------------------------------------ */
function SettingsPanel({ value, onSave, saving }) {
  const [form, setForm] = useState(value);
  useEffect(() => setForm(value), [value]);

  const update = (patch) => setForm((prev) => ({ ...prev, ...patch }));
  const toggleIn = (key, item) => {
    const list = form[key] || [];
    update({ [key]: list.includes(item) ? list.filter((x) => x !== item) : [...list, item] });
  };
  const slotsText = (form.slots || []).join(', ');

  return (
    <div className="space-y-5 p-5">
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Platform publikasi" hint="Facebook belum tersedia; pilihan disimpan untuk persiapan.">
          <div className="flex flex-wrap gap-2">
            {value.available_platforms.map((p) => {
              const active = (form.platforms || []).includes(p.key);
              const Icon = p.key === 'instagram' ? Instagram : Facebook;
              return (
                <button
                  key={p.key}
                  type="button"
                  disabled={!p.available}
                  onClick={() => toggleIn('platforms', p.key)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition',
                    active ? 'border-brand-400 bg-brand-50 text-brand-700' : 'border-line bg-surface text-ink-muted',
                    !p.available && 'cursor-not-allowed opacity-50'
                  )}
                >
                  <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  {p.label}
                  {!p.available && <span className="text-[10px] font-normal">(belum tersedia)</span>}
                </button>
              );
            })}
          </div>
        </Field>

        <Field label="Frekuensi publikasi per minggu" hint="Batas jumlah konten yang diproduksi otomatis.">
          <input
            type="number"
            min="1"
            max="21"
            value={form.frequency_per_week ?? 5}
            onChange={(e) => update({ frequency_per_week: Number(e.target.value) })}
            className="input"
          />
        </Field>
      </div>

      <Field label="Hari publikasi">
        <div className="flex flex-wrap gap-1.5">
          {DAYS.map((d) => {
            const active = (form.posting_days || []).includes(d.value);
            return (
              <button
                key={d.value}
                type="button"
                aria-pressed={active}
                onClick={() => toggleIn('posting_days', d.value)}
                className={cn(
                  'h-9 w-11 rounded-lg border text-xs font-semibold transition',
                  active ? 'border-brand-400 bg-brand-50 text-brand-700' : 'border-line bg-surface text-ink-muted'
                )}
              >
                {d.label}
              </button>
            );
          })}
        </div>
      </Field>

      <Field
        label="Jam publikasi"
        hint="Pisahkan dengan koma, format 24 jam (contoh: 09:00, 19:00). Waktu mengikuti zona waktu di server."
      >
        <input
          type="text"
          value={slotsText}
          onChange={(e) => update({ slots: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
          placeholder="09:00, 19:00"
          className="input"
        />
      </Field>

      <Field label="Jenis konten yang diproduksi">
        <div className="flex flex-wrap gap-2">
          {FORMATS.map((f) => {
            const active = (form.content_formats || []).includes(f.value);
            return (
              <button
                key={f.value}
                type="button"
                aria-pressed={active}
                onClick={() => toggleIn('content_formats', f.value)}
                className={cn(
                  'rounded-lg border px-3 py-1.5 text-xs font-semibold transition',
                  active ? 'border-brand-400 bg-brand-50 text-brand-700' : 'border-line bg-surface text-ink-muted'
                )}
              >
                {f.label}
              </button>
            );
          })}
        </div>
      </Field>

      <div className="grid gap-3 rounded-xl bg-canvas p-3.5 sm:grid-cols-2">
        <Switch
          checked={Boolean(form.require_approval)}
          onChange={(v) => update({ require_approval: v })}
          label="Wajib persetujuan sebelum publikasi"
          description="Sangat disarankan. Bila dimatikan, konten yang dijadwalkan akan tayang tanpa Anda periksa."
        />
        <Switch
          checked={Boolean(form.auto_generate)}
          onChange={(v) => update({ auto_generate: v })}
          label="Buat konten otomatis"
          description="AI menyiapkan konten sesuai kalender tanpa Anda tekan tombol."
        />
      </div>

      <div className="flex flex-col gap-2 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[11px] leading-relaxed text-ink-muted">
          Perubahan berlaku pada siklus otomatisasi berikutnya (≤1 menit).
        </p>
        <Button icon={Settings2} loading={saving}
          onClick={() => onSave({
            platforms: form.platforms,
            posting_days: form.posting_days,
            slots: form.slots,
            frequency_per_week: form.frequency_per_week,
            content_formats: form.content_formats,
            require_approval: form.require_approval,
            auto_generate: form.auto_generate,
          })}>
          Simpan pengaturan
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Halaman                                                             */
/* ------------------------------------------------------------------ */
export default function Automation({ onNotify, onOpenRun }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [calendarBusy, setCalendarBusy] = useState(false);
  const [approvingAll, setApprovingAll] = useState(false);
  const [filter, setFilter] = useState('upcoming');

  // Modal Ubah Jadwal
  const [rescheduleTarget, setRescheduleTarget] = useState(null);
  const [rescheduleDate, setRescheduleDate] = useState('');
  const [rescheduleSlot, setRescheduleSlot] = useState('');
  const [rescheduleSaving, setRescheduleSaving] = useState(false);

  // Modal Preview Hasil Konten
  const [previewTarget, setPreviewTarget] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState(null);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    try {
      const res = await api.getAutomation();
      setData(res);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Polling ringan: status berubah dari backend (scheduler/eksekusi manual).
  useEffect(() => {
    const id = window.setInterval(() => load({ silent: true }), 15000);
    return () => window.clearInterval(id);
  }, [load]);

  const settings = data?.settings;
  const summary = data?.summary;
  const week = useMemo(() => data?.week || [], [data]);
  const counts = data?.week_counts || {};
  const live = data?.live || { active_runs: [], publishing_count: 0, idle: true };
  const stateMeta = automationStateMeta(settings?.state);
  const running = settings?.is_running;
  const needsApproval = counts.needs_approval || 0;

  const rows = useMemo(() => {
    if (filter === 'needs_approval') return week.filter((r) => r.status === 'needs_approval');
    if (filter === 'scheduled') return week.filter((r) => ['scheduled', 'publishing'].includes(r.status));
    if (filter === 'published') return week.filter((r) => r.status === 'published');
    return week.filter((r) => r.status !== 'published');
  }, [week, filter]);

  /* ---- aksi ---- */
  const approveRow = async (row, kind) => {
    setBusy(`approve-${kind === 'item' ? 'item' : 'pub'}-${row.ref_id}`);
    try {
      if (kind === 'item') {
        await api.updateStrategyItem(row.ref_id, { status: 'approved' });
        onNotify?.('success', 'Ide konten disetujui. AI akan menyiapkan kontennya sesuai jadwal.', 'Disetujui');
      } else {
        const res = await api.approvePublication(row.publication_id, { publish_now: false });
        onNotify?.('success', res.message || 'Konten disetujui dan dijadwalkan.', 'Disetujui');
      }
      await load({ silent: true });
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal menyetujui');
    } finally {
      setBusy(null);
    }
  };

  const editTopic = async (row, topic) => {
    setBusy(`topic-${row.ref_id}`);
    try {
      await api.updateStrategyItem(row.ref_id, { topic });
      onNotify?.('success', 'Topik konten diperbarui.', 'Tersimpan');
      await load({ silent: true });
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal mengubah topik');
    } finally {
      setBusy(null);
    }
  };

  const openRescheduleModal = (row) => {
    setRescheduleTarget(row);
    setRescheduleDate(row.date || new Date().toISOString().split('T')[0]);
    setRescheduleSlot(row.slot || '09:00');
  };

  const saveReschedule = async () => {
    if (!rescheduleTarget) return;
    setRescheduleSaving(true);
    try {
      if (rescheduleTarget.kind === 'publication' && rescheduleTarget.publication_id) {
        // Gunakan offset +07:00 (WIB / Asia/Jakarta) agar waktu jam tidak bergeser 7 jam ke UTC
        const iso = `${rescheduleDate}T${rescheduleSlot || '09:00'}:00+07:00`;
        await api.updatePublication(rescheduleTarget.publication_id, { scheduled_for: iso });
      } else {
        const slotText = rescheduleSlot ? `${rescheduleSlot} WIB` : undefined;
        await api.updateStrategyItem(rescheduleTarget.ref_id, {
          plan_date: rescheduleDate,
          scheduled_slot: slotText,
        });
      }
      onNotify?.('success', 'Jadwal tayang berhasil diperbarui.', 'Jadwal Diubah');
      setRescheduleTarget(null);
      await load({ silent: true });
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal mengubah jadwal');
    } finally {
      setRescheduleSaving(false);
    }
  };

  const openPreviewModal = async (row) => {
    setPreviewTarget(row);
    setPreviewData(null);
    setPreviewLoading(true);
    try {
      if (row.run_id) {
        const status = await api.getRunStatus(row.run_id);
        setPreviewData({ type: 'run', ...status });
      } else if (row.publication_id) {
        const pub = await api.getPublication(row.publication_id);
        setPreviewData({ type: 'publication', ...pub });
      }
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal memuat pratinjau hasil');
    } finally {
      setPreviewLoading(false);
    }
  };

  const cancelRow = async (row) => {
    setBusy(`cancel-${row.publication_id}`);
    try {
      await api.cancelPublication(row.publication_id);
      onNotify?.('info', 'Publikasi dibatalkan. Konten tidak akan tayang.', 'Dibatalkan');
      await load({ silent: true });
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal membatalkan');
    } finally {
      setBusy(null);
    }
  };

  const publishRow = async (row) => {
    setBusy(`publish-${row.publication_id}`);
    try {
      const res = await api.publishPublication(row.publication_id);
      if (res.ok) onNotify?.('success', 'Konten sudah tayang di Instagram.', 'Publikasi berhasil');
      else onNotify?.('error', res.error || 'Publikasi gagal.', 'Publikasi gagal');
      await load({ silent: true });
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal mempublikasikan');
    } finally {
      setBusy(null);
    }
  };

  const control = async (action, label) => {
    setBusy(action);
    try {
      const res = await api.automationControl(action);
      setData(res);
      onNotify?.(
        action === 'stop' ? 'warning' : 'success',
        action === 'stop'
          ? 'Otomatisasi dihentikan dan jadwal yang belum tayang dibatalkan.'
          : `Otomatisasi ${label}.`,
        'Pusat Otomatisasi'
      );
    } catch (err) {
      onNotify?.('error', err.message, `Gagal ${label}`);
    } finally {
      setBusy(null);
    }
  };

  const toggleEnabled = async (next) => {
    setBusy('toggle');
    try {
      const res = await api.updateAutomation({ enabled: next });
      setData(res);
      onNotify?.('success', next ? 'Otomatisasi diaktifkan. AI mulai bekerja sesuai kalender.' : 'Otomatisasi dijeda.',
        'Pusat Otomatisasi');
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal mengubah status otomatisasi');
    } finally {
      setBusy(null);
    }
  };

  // Susun jadwal 7 hari memakai kuota LLM: minta konfirmasi dulu agar tidak tak sengaja.
  const generateCalendar = async () => {
    if (!window.confirm('Susun jadwal 7 hari baru? Ide konten minggu ini akan dibuat ulang oleh AI.')) return;
    setCalendarBusy(true);
    try {
      await api.regenerateStrategyCalendar();
      onNotify?.('success', 'Jadwal 7 hari sudah disusun. Tinjau idenya lalu klik Setujui Semua.', 'Jadwal dibuat');
      await load({ silent: true });
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal menyusun jadwal');
    } finally {
      setCalendarBusy(false);
    }
  };

  const approveAll = async () => {
    setApprovingAll(true);
    try {
      const res = await api.approveAllPublications();
      const total = (res.approved_publications || 0) + (res.approved_calendar_items || 0);
      if (total === 0) {
        onNotify?.('info', 'Tidak ada konten yang perlu disetujui saat ini.', 'Tidak ada perubahan');
      } else {
        onNotify?.('success',
          `${res.approved_calendar_items || 0} ide + ${res.approved_publications || 0} publikasi disetujui. `
          + 'Konten akan dibuat dan tayang sesuai jadwal.',
          'Setujui semua berhasil');
      }
      if ((res.errors || []).length) {
        onNotify?.('warning', `${res.errors.length} konten gagal disetujui. Lihat detail di tabel.`, 'Sebagian gagal');
      }
      if (res.settings) setData(res);
      else await load({ silent: true });
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal menyetujui semua');
    } finally {
      setApprovingAll(false);
    }
  };

  const saveSettings = async (patch) => {
    setSavingSettings(true);
    try {
      const res = await api.updateAutomation(patch);
      setData(res);
      onNotify?.('success', 'Pengaturan otomatisasi disimpan.', 'Tersimpan');
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal menyimpan pengaturan');
    } finally {
      setSavingSettings(false);
    }
  };

  if (loading && !data) {
    return (
      <div className="space-y-4">
        <PageHeader title="Pusat Otomatisasi" description="Memuat pengaturan dan jadwal…" />
        <div className="card h-36 animate-pulse" aria-hidden="true" />
        <div className="card h-64 animate-pulse" aria-hidden="true" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="space-y-4">
        <PageHeader title="Pusat Otomatisasi" description="Kendalikan aktivitas marketing otomatis Anda." />
        <EmptyState
          icon={AlertTriangle}
          title="Pusat Otomatisasi tidak bisa dimuat"
          description={error}
          action={<Button icon={RefreshCw} onClick={() => load()}>Coba lagi</Button>}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Pusat Otomatisasi"
        description="Mulai autopilot, tinjau jadwal minggu ini, dan setujui konten tanpa berpindah halaman."
        actions={
          <>
            <Button variant="secondary" size="sm" icon={RefreshCw} onClick={() => load()} loading={loading}>
              Muat ulang
            </Button>
            <Button size="sm" variant="secondary" icon={Settings2} onClick={() => setShowSettings((v) => !v)}>
              {showSettings ? 'Tutup aturan' : 'Aturan'}
            </Button>
          </>
        }
      />

      {/* 1. HERO / MASTER TOGGLE */}
      <Card>
        <div className={cn('p-5', running ? 'bg-success-50/40' : 'bg-surface')}>
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-3">
              <span className={cn('flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl',
                running ? 'bg-success-100 text-success-700' : 'bg-soft text-ink-muted')}>
                <Power className="h-6 w-6" aria-hidden="true" />
              </span>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-lg font-semibold text-ink">Autopilot konten</p>
                  <StatusBadge meta={stateMeta} dot />
                </div>
                <p className="mt-1 max-w-2xl text-sm leading-relaxed text-ink-muted">
                  {running
                    ? `Mode autopilot aktif: ${counts.scheduled || 0} konten terjadwal minggu ini, ${counts.published || 0} sudah tayang.`
                    : settings?.state === 'stopped'
                      ? 'Otomatisasi dihentikan. Publikasi terjadwal yang belum tayang sudah dibatalkan.'
                      : 'Sistem akan otomatis meriset, mendesain, dan memposting sesuai kalender mingguan usaha Anda.'}
                </p>
                {data?.next_slot && (
                  <p className="mt-1.5 text-[11px] text-ink-muted">
                    Slot berikutnya: <strong className="text-ink">{fmtTime(data.next_slot)}</strong>
                    {needsApproval > 0 && (
                      <>
                        {' · '}
                        <span className="font-semibold text-warning-700">
                          {needsApproval} konten menunggu persetujuan Anda
                        </span>
                      </>
                    )}
                  </p>
                )}
                {settings && !settings.scheduler_process_enabled && (
                  <p className="mt-1.5 text-[11px] text-warning-700">
                    Penjadwal backend belum aktif (SCHEDULER_ENABLED=false) — konten terjadwal tidak akan tayang
                    otomatis sampai fitur ini dinyalakan di server.
                  </p>
                )}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {!running ? (
                <Button size="lg" variant="success" icon={Play} loading={busy === 'resume' || busy === 'toggle'}
                  onClick={() => control('resume', 'dimulai')}>
                  Mulai Otomatisasi 7 Hari
                </Button>
              ) : (
                <Button size="lg" variant="secondary" icon={Pause} loading={busy === 'pause'}
                  onClick={() => control('pause', 'dijeda')}>
                  Jeda
                </Button>
              )}
              <Button size="sm" variant="danger" icon={Square} loading={busy === 'stop'}
                disabled={settings?.state === 'stopped'}
                onClick={() => control('stop', 'dihentikan')}>
                Stop
              </Button>
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between gap-4 border-t border-line pt-4">
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink">Aktifkan otomatisasi</p>
              <p className="text-xs text-ink-muted">Sakelar utama. Nonaktif = tidak ada konten yang dipublikasikan otomatis.</p>
            </div>
            <Switch checked={Boolean(settings?.enabled)} onChange={toggleEnabled} disabled={busy === 'toggle'}
              label="Aktifkan otomatisasi" />
          </div>
        </div>
      </Card>

      {/* 2. QUICK ACTIONS */}
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <Button size="md" icon={CalendarPlus} loading={calendarBusy} onClick={generateCalendar}
          className="w-full sm:w-auto">
          Susun Jadwal 7 Hari
        </Button>
        <Button size="md" variant={needsApproval > 0 ? 'primary' : 'secondary'} icon={CheckCircle2}
          loading={approvingAll} onClick={approveAll} className="w-full sm:w-auto">
          Setujui Semua{needsApproval > 0 ? ` (${needsApproval})` : ''}
        </Button>
        <Button size="md" variant="secondary" icon={Settings2} onClick={() => setShowSettings((v) => !v)}
          className="w-full sm:w-auto">
          Aturan
        </Button>
      </div>

      {/* 3. JADWAL & PERSETUJUAN */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Jadwal & persetujuan minggu ini"
            description="Senin sampai Minggu: format, topik, dan status robotnya."
            icon={CalendarClock}
            actions={
              <div className="inline-flex flex-wrap rounded-lg border border-line bg-canvas p-0.5">
                {[
                  { key: 'upcoming', label: 'Aktif' },
                  { key: 'needs_approval', label: 'Perlu disetujui' },
                  { key: 'scheduled', label: 'Terjadwal' },
                  { key: 'published', label: 'Tayang' },
                ].map((opt) => (
                  <button
                    key={opt.key}
                    type="button"
                    onClick={() => setFilter(opt.key)}
                    className={cn('rounded-md px-2.5 py-1 text-xs font-semibold transition',
                      filter === opt.key ? 'bg-surface text-ink shadow-card' : 'text-ink-muted hover:text-ink')}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            }
          />
          {rows.length === 0 ? (
            <div className="p-5">
              <EmptyState
                icon={CalendarClock}
                title={week.length === 0 ? 'Belum ada jadwal minggu ini' : 'Tidak ada konten di filter ini'}
                description={week.length === 0
                  ? 'Klik "Susun Jadwal 7 Hari" — AI membuat 5–7 ide konten yang bisa Anda setujui sekaligus.'
                  : 'Coba pilih filter lain untuk melihat konten lainnya.'}
                className="border-0 bg-transparent"
              />
            </div>
          ) : (
            <ul className="divide-y divide-line">
              {rows.map((row) => (
                <WeekRow
                  key={`${row.kind}-${row.ref_id}`}
                  row={row}
                  busy={busy}
                  onApprove={approveRow}
                  onCancel={cancelRow}
                  onPublish={publishRow}
                  onEditTopic={editTopic}
                  onReschedule={openRescheduleModal}
                  onPreview={openPreviewModal}
                />
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-4">
          {/* Ringkasan angka */}
          <div className="grid grid-cols-2 gap-3">
            <StatCard label="Perlu disetujui" value={needsApproval} helper="Tunggu keputusan Anda"
              icon={Clock} tone="warning" />
            <StatCard label="Terjadwal" value={counts.scheduled ?? 0} helper="Tayang otomatis"
              icon={CalendarClock} tone="brand" />
            <StatCard label="Sudah tayang" value={counts.published ?? 0} helper="Ada di Instagram"
              icon={CheckCircle2} tone="success" />
            <StatCard label="Gagal" value={counts.failed ?? 0} helper="Perlu ditinjau"
              icon={AlertTriangle} tone="danger" />
          </div>

          {/* Riwayat aktivitas */}
          <Card>
            <CardHeader title="Riwayat aktivitas" icon={History} description="Jejak tindakan terakhir." />
            {(data?.activity || []).length === 0 ? (
              <div className="p-4">
                <p className="text-xs leading-relaxed text-ink-muted">
                  Belum ada aktivitas. Setiap perubahan pengaturan, persetujuan, publikasi, dan
                  pembatalan akan tercatat di sini.
                </p>
              </div>
            ) : (
              <ul className="max-h-[22rem] divide-y divide-line overflow-y-auto">
                {(data?.activity || []).map((event) => {
                  const tone = event.status === 'error' ? 'danger' : event.status === 'warning' ? 'warning' : 'neutral';
                  return (
                    <li key={event.id} className="px-4 py-2.5">
                      <div className="flex items-start justify-between gap-2">
                        <p className="min-w-0 text-xs leading-relaxed text-ink">
                          {truncate(event.message || event.action, 110)}
                        </p>
                        <Badge tone={tone} className="shrink-0 text-[10px]">{event.action.replace(/_/g, ' ')}</Badge>
                      </div>
                      <p className="mt-0.5 text-[11px] text-ink-subtle">
                        {timeAgo(event.created_at)} · {event.actor}
                      </p>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {/* 4. LIVE PIPELINE STATUS */}
      <Card>
        <CardHeader
          title="Status proses (live)"
          description="Apa yang sedang dikerjakan robot sekarang."
          icon={Sparkles}
          actions={
            <Button size="xs" variant="secondary" icon={RefreshCw} onClick={() => load({ silent: true })}>
              Segarkan
            </Button>
          }
        />
        <div className="p-5">
          {live.idle ? (
            <p className="text-sm text-ink-muted">
              Tidak ada proses berjalan saat ini. Konten yang terjadwal akan diproses otomatis oleh penjadwal.
            </p>
          ) : (
            <ul className="space-y-3">
              {(live.active_runs || []).map((run) => (
                <li key={run.run_id} className="rounded-xl border border-line bg-canvas/60 p-3.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="min-w-0 text-sm font-semibold text-ink">{truncate(run.topic, 70)}</p>
                    <div className="flex items-center gap-2">
                      <Badge tone="brand" className="text-[10px] uppercase">{run.step}</Badge>
                      {onOpenRun && (
                        <Button size="xs" variant="secondary" onClick={() => onOpenRun(run.run_id)}>
                          Lihat detail
                        </Button>
                      )}
                    </div>
                  </div>
                  <p className="mt-1 flex items-center gap-1.5 text-xs text-ink-muted">
                    <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                    {run.stage}
                    {run.started_at && <span className="text-ink-subtle">· mulai {timeAgo(run.started_at)}</span>}
                  </p>
                  {/* Pelacak tahap dari step nyata di event log (bukan persentase karangan). */}
                  <ol className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="Tahap proses">
                    {PIPELINE_STAGES.map((stage, index) => {
                      const current = index === stageIndex(run.step);
                      const done = index < stageIndex(run.step);
                      return (
                        <li
                          key={stage.key}
                          className={cn(
                            'rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                            current && 'bg-brand-100 text-brand-800',
                            done && 'bg-success-50 text-success-700',
                            !current && !done && 'bg-soft text-ink-subtle'
                          )}
                          aria-current={current ? 'step' : undefined}
                        >
                          {stage.label}
                        </li>
                      );
                    })}
                  </ol>
                </li>
              ))}
              {live.publishing_count > 0 && (
                <li className="rounded-xl border border-brand-200 bg-brand-50 p-3.5 text-sm text-brand-900">
                  {live.publishing_count} konten sedang dipublikasikan ke Instagram.
                </li>
              )}
            </ul>
          )}
        </div>
      </Card>

      {/* Pengaturan minimalis */}
      {showSettings && settings && (
        <Card>
          <CardHeader title="Aturan otomatisasi" icon={Settings2}
            description="Jadwal, platform, jenis konten, dan aturan persetujuan." />
          <SettingsPanel value={settings} onSave={saveSettings} saving={savingSettings} />
        </Card>
      )}

      {summary?.queued_generation > 0 && (
        <Alert tone="info" title={`${summary.queued_generation} konten menunggu diproduksi`}>
          AI akan membuat konten ini sesuai urutan jadwal. Anda dapat menutup browser — proses berjalan di server.
        </Alert>
      )}

      {/* Modal Ubah Jadwal Tayang */}
      <Modal
        open={Boolean(rescheduleTarget)}
        onClose={() => setRescheduleTarget(null)}
        title="Ubah Jadwal Tayang"
        icon={Calendar}
        description={`Atur ulang tanggal atau jam tayang untuk: ${truncate(rescheduleTarget?.topic, 60)}`}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRescheduleTarget(null)}>Batal</Button>
            <Button loading={rescheduleSaving} onClick={saveReschedule}>Simpan Jadwal</Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field label="Tanggal Tayang">
            <input
              type="date"
              className="input"
              value={rescheduleDate}
              onChange={(e) => setRescheduleDate(e.target.value)}
            />
          </Field>
          <Field label="Jam Tayang" hint="Format jam:menit (misal: 09:00 atau 18:30)">
            <input
              type="time"
              className="input"
              value={rescheduleSlot}
              onChange={(e) => setRescheduleSlot(e.target.value)}
            />
          </Field>
        </div>
      </Modal>

      {/* Modal Pratinjau Hasil Konten */}
      <Modal
        open={Boolean(previewTarget)}
        onClose={() => { setPreviewTarget(null); setPreviewData(null); }}
        title="Pratinjau Hasil Konten"
        icon={Eye}
        size="lg"
        description={previewTarget?.topic}
        footer={
          <div className="flex w-full items-center justify-between">
            {previewTarget?.run_id && onOpenRun && (
              <Button
                variant="ghost"
                size="sm"
                icon={ExternalLink}
                onClick={() => {
                  const runId = previewTarget.run_id;
                  setPreviewTarget(null);
                  onOpenRun(runId);
                }}
              >
                Buka di Editor / Riwayat
              </Button>
            )}
            <Button variant="secondary" onClick={() => { setPreviewTarget(null); setPreviewData(null); }}>
              Tutup
            </Button>
          </div>
        }
      >
        {previewLoading ? (
          <div className="flex h-56 flex-col items-center justify-center gap-2 text-ink-muted">
            <Loader2 className="h-6 w-6 animate-spin text-brand-600" />
            <p className="text-sm">Memuat visual dan caption...</p>
          </div>
        ) : !previewData ? (
          <EmptyState
            icon={AlertTriangle}
            title="Pratinjau belum tersedia"
            description="Konten ini mungkin belum selesai digenerate atau belum memiliki aset media."
          />
        ) : (
          <div className="space-y-4">
            {/* Visual Carousel atau Video */}
            {previewData.type === 'run' && previewData.video?.url && (
              <div className="overflow-hidden rounded-xl bg-black">
                <video src={mediaUrl(previewData.video.url)} controls className="max-h-[380px] w-full object-contain" />
              </div>
            )}

            {previewData.type === 'run' && previewData.design?.slides && previewData.design.slides.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-ink-muted uppercase tracking-wider">
                  Slide Carousel ({previewData.design.slides.length} slide)
                </p>
                <div className="flex gap-2 overflow-x-auto pb-2">
                  {previewData.design.slides.map((s, idx) => (
                    <div key={idx} className="relative h-44 w-36 shrink-0 overflow-hidden rounded-lg border border-line bg-canvas">
                      {s.image_url ? (
                        <img src={mediaUrl(s.image_url)} alt={`Slide ${idx + 1}`} className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full items-center justify-center p-2 text-center text-xs text-ink-muted">
                          Slide {idx + 1}
                        </div>
                      )}
                      <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
                        {idx + 1}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {previewData.type === 'publication' && previewData.image_urls && previewData.image_urls.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-ink-muted uppercase tracking-wider">
                  Slide Media ({previewData.image_urls.length} gambar)
                </p>
                <div className="flex gap-2 overflow-x-auto pb-2">
                  {previewData.image_urls.map((url, idx) => (
                    <div key={idx} className="relative h-44 w-36 shrink-0 overflow-hidden rounded-lg border border-line bg-canvas">
                      <img src={url} alt={`Slide ${idx + 1}`} className="h-full w-full object-cover" />
                      <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
                        {idx + 1}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Caption & Hashtag */}
            <div className="rounded-xl border border-line bg-canvas/70 p-3.5">
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Teks Caption</p>
              <p className="mt-1.5 whitespace-pre-line text-xs leading-relaxed text-ink">
                {previewData.type === 'publication'
                  ? previewData.caption
                  : (previewData.plan?.caption || previewData.video?.suggested_caption || 'Belum ada caption')}
              </p>
              {previewData.plan?.hashtags && previewData.plan.hashtags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {previewData.plan.hashtags.map((h, i) => (
                    <span key={i} className="text-[11px] text-brand-600">#{h.replace(/^#/, '')}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
