import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Ban,
  CalendarClock,
  CheckCircle2,
  Clock,
  Facebook,
  History,
  Instagram,
  Loader2,
  Pause,
  Play,
  Power,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Sparkles,
  Square,
  X,
} from 'lucide-react';
import { api } from '../api';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Field,
  PageHeader,
  Pills,
  ProgressBar,
  Segmented,
  Spinner,
  StatCard,
  StatusBadge,
  Switch,
} from '../components/ui';
import { automationStateMeta, fmtTime, publicationStatusMeta, timeAgo, truncate } from '../lib/format';
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

function PublicationRow({ pub, onApprove, onCancel, busy, showCountdown }) {
  const meta = publicationStatusMeta(pub.status);
  const Icon = {
    check: CheckCircle2, clock: Clock, calendar: CalendarClock, loader: Loader2,
    alert: AlertTriangle, x: X, ban: Ban, info: Clock,
  }[meta.icon] || Clock;
  const canAct = pub.can_publish || pub.can_cancel;

  return (
    <li className="flex flex-col gap-2.5 px-4 py-3.5 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <span className={cn('mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', STATUS_TONE[meta.tone])}>
          <Icon className={cn('h-4 w-4', pub.status === 'publishing' && 'animate-spin')} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold leading-snug text-ink">
            {truncate(pub.topic || pub.caption || `Publikasi #${pub.id}`, 90)}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusBadge meta={{ label: pub.status_label || meta.label, tone: meta.tone }} dot />
            <Badge tone="neutral" className="bg-canvas text-[10px] uppercase">
              {pub.media_type || pub.format || 'carousel'}
            </Badge>
            <Badge tone="neutral" className="bg-canvas text-[10px] uppercase">{pub.platform}</Badge>
            {pub.scheduled_for && (
              <span className="text-[11px] text-ink-muted">
                Jadwal {fmtTime(pub.scheduled_for)}
              </span>
            )}
            {pub.published_at && (
              <span className="text-[11px] text-ink-muted">Tayang {timeAgo(pub.published_at)}</span>
            )}
          </div>
          {pub.error && (
            <p className="mt-1.5 line-clamp-2 break-words text-[11px] leading-relaxed text-danger-600">
              {pub.error}
            </p>
          )}
          {pub.permalink && (
            <a
              href={pub.permalink}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-block text-[11px] font-semibold text-brand-700 hover:underline"
            >
              Lihat di Instagram →
            </a>
          )}
        </div>
      </div>

      {canAct && (
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 sm:pt-0.5">
          {pub.can_publish && (
            <Button size="xs" icon={CheckCircle2} loading={busy === `approve-${pub.id}`}
              onClick={() => onApprove(pub)}>
              Setujui & Publikasikan
            </Button>
          )}
          {pub.can_cancel && (
            <Button size="xs" variant="secondary" icon={Ban} loading={busy === `cancel-${pub.id}`}
              onClick={() => onCancel(pub)}>
              Batalkan
            </Button>
          )}
        </div>
      )}
      {showCountdown && !pub.can_publish && !pub.can_cancel && pub.status === 'published' && (
        <span className="shrink-0 text-[11px] text-ink-subtle">Selesai</span>
      )}
    </li>
  );
}

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

        <Field label="Frekuensi publikasi per minggu" hint="Batas jumlah konten yang diproduksi otomatis.")
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
        hint="Pisahkan dengan koma, format 24 jam (contoh: 09:00, 19:00). Waktu mengikuti zona waktu di bawah."
      >
        <input
          type="text"
          value={slotsText}
          onChange={(e) => update({ slots: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
          placeholder="09:00, 19:00"
          className="input font-mono text-sm"
        />
      </Field>

      <Field label="Jenis konten yang dibuat otomatis">
        <div className="flex flex-wrap gap-1.5">
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

export default function Automation({ onNotify, onOpenRun }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [tab, setTab] = useState('pending');
  const [showSettings, setShowSettings] = useState(false);

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

  // Polling ringan: status publikasi berubah dari backend (scheduler/eksekusi manual).
  useEffect(() => {
    const id = window.setInterval(() => load({ silent: true }), 15000);
    return () => window.clearInterval(id);
  }, [load]);

  const settings = data?.settings;
  const summary = data?.summary;
  const stateMeta = automationStateMeta(settings?.state);
  const running = settings?.is_running;

  const approve = async (pub) => {
    setBusy(`approve-${pub.id}`);
    try {
      const res = await api.approvePublication(pub.id, { publish_now: !pub.scheduled_for });
      if (res.ok) {
        onNotify?.('success', res.message || 'Konten disetujui dan dikirim ke Instagram.', 'Publikasi berhasil');
      } else {
        onNotify?.('error', res.error || 'Publikasi gagal. Periksa detail pada kartu konten.', 'Publikasi gagal');
      }
      await load({ silent: true });
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal menyetujui publikasi');
    } finally {
      setBusy(null);
    }
  };

  const cancel = async (pub) => {
    setBusy(`cancel-${pub.id}`);
    try {
      await api.cancelPublication(pub.id);
      onNotify?.('info', 'Publikasi dibatalkan. Konten tidak akan tayang.', 'Dibatalkan');
      await load({ silent: true });
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal membatalkan publikasi');
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
        action === 'stop' ? 'Otomatisasi dihentikan dan jadwal yang belum tayang dibatalkan.' : `Otomatisasi ${label}.`,
        'Pusat Otomatisasi'
      );
    } catch (err) {
      onNotify?.('error', err.message, `Gagal ${label}`);
    } finally {
      setBusy(null);
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

  const toggleEnabled = async (next) => {
    setBusy('toggle');
    try {
      const res = await api.updateAutomation({ enabled: next });
      setData(res);
      onNotify?.('success', next ? 'Otomatisasi diaktifkan.' : 'Otomatisasi dinonaktifkan.', 'Pusat Otomatisasi');
    } catch (err) {
      onNotify?.('error', err.message, 'Gagal mengubah status otomatisasi');
    } finally {
      setBusy(null);
    }
  };

  const listFor = useMemo(() => {
    if (!data) return [];
    if (tab === 'pending') return data.pending_approvals || [];
    if (tab === 'scheduled') return data.scheduled || [];
    return [];
  }, [data, tab]);

  if (loading && !data) {
    return (
      <div className="space-y-4">
        <PageHeader title="Pusat Otomatisasi" description="Memuat pengaturan dan antrian publikasi…" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="card h-28 animate-pulse" aria-hidden="true" />)}
        </div>
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
        description="Semua kendali marketing otomatis dalam satu halaman. Setiap tombol terhubung langsung ke backend."
        actions={
          <>
            <Button variant="secondary" size="sm" icon={RefreshCw} onClick={() => load()} loading={loading}>
              Muat ulang
            </Button>
            <Button size="sm" variant="secondary" icon={Settings2} onClick={() => setShowSettings((v) => !v)}>
              {showSettings ? 'Tutup pengaturan' : 'Pengaturan'}
            </Button>
          </>
        }
      />

      {/* Kartu status utama */}
      <Card className="p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <span className={cn('flex h-11 w-11 shrink-0 items-center justify-center rounded-xl',
              running ? 'bg-success-50 text-success-600' : 'bg-soft text-ink-muted')}>
              <Power className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-base font-semibold text-ink">Status otomatisasi</p>
                <StatusBadge meta={stateMeta} dot />
              </div>
              <p className="mt-1 max-w-xl text-xs leading-relaxed text-ink-muted">
                {running
                  ? 'Otomatisasi berjalan. Konten yang dijadwalkan akan dipublikasikan sesuai jam yang Anda atur.'
                  : settings?.state === 'stopped'
                    ? 'Otomatisasi dihentikan. Publikasi terjadwal yang belum tayang sudah dibatalkan.'
                    : 'Otomatisasi dijeda. Jadwal dan antrian tetap tersimpan sampai Anda melanjutkan.'}
              </p>
              {data?.next_slot && (
                <p className="mt-1.5 text-[11px] text-ink-muted">
                  Slot berikutnya: <strong className="text-ink">{fmtTime(data.next_slot)}</strong>
                </p>
              )}
              {settings && !settings.scheduler_process_enabled && (
                <p className="mt-1.5 text-[11px] text-warning-700">
                  Penjadwal backend belum aktif di server (SCHEDULER_ENABLED=false), jadi publikasi
                  otomatis belum akan berjalan walau status di sini “Berjalan”.
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant={running ? 'secondary' : 'success'}
              icon={Play}
              loading={busy === 'resume' || busy === 'toggle'}
              disabled={running}
              onClick={() => control('resume', 'dilanjutkan')}
            >
              Resume
            </Button>
            <Button
              size="sm"
              variant="secondary"
              icon={Pause}
              loading={busy === 'pause'}
              disabled={!running}
              onClick={() => control('pause', 'dijeda')}
            >
              Pause
            </Button>
            <Button
              size="sm"
              variant="danger"
              icon={Square}
              loading={busy === 'stop'}
              disabled={settings?.state === 'stopped'}
              onClick={() => control('stop', 'dihentikan')}
            >
              Stop
            </Button>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between gap-4 border-t border-line pt-4">
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">Aktifkan otomatisasi</p>
            <p className="text-xs text-ink-muted">Sakelar utama. Nonaktif = tidak ada konten yang dipublikasikan otomatis.</p>
          </div>
          <Switch checked={Boolean(settings?.enabled)} onChange={toggleEnabled} disabled={busy === 'toggle'} label="Aktifkan otomatisasi" />
        </div>
      </Card>

      {/* Ringkasan angka */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-5">
        <StatCard label="Konten diproses" value={summary?.total_processed ?? 0} helper="Total item konten"
          icon={Sparkles} tone="neutral" />
        <StatCard label="Menunggu persetujuan" value={summary?.awaiting_approval ?? 0} helper="Perlu keputusan Anda"
          icon={Clock} tone="warning" />
        <StatCard label="Terjadwal" value={summary?.scheduled ?? 0} helper="Akan tayang otomatis"
          icon={CalendarClock} tone="brand" />
        <StatCard label="Berhasil" value={summary?.published ?? 0} helper="Sudah tayang di Instagram"
          icon={CheckCircle2} tone="success" />
        <StatCard label="Gagal" value={summary?.failed ?? 0} helper="Perlu ditinjau"
          icon={AlertTriangle} tone="danger" />
      </div>

      {(summary?.publishing ?? 0) > 0 && (
        <Alert tone="info" title={`${summary.publishing} konten sedang dipublikasikan`}>
          Proses publikasi sedang berjalan di server. Status akan diperbarui otomatis pada halaman ini.
          <ProgressBar value={70} className="mt-2" />
        </Alert>
      )}

      {showSettings && settings && (
        <Card>
          <CardHeader title="Pengaturan otomatisasi" icon={Settings2}
            description="Jadwal, platform, jenis konten, dan aturan persetujuan." />
          <SettingsPanel value={settings} onSave={saveSettings} saving={savingSettings} />
        </Card>
      )}

      {/* Antrian kerja */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Antrian publikasi"
            description="Konten menunggu persetujuan dan yang sudah dijadwalkan."
            icon={ShieldCheck}
            actions={
              <Pills
                ariaLabel="Filter antrian"
                value={tab}
                onChange={setTab}
                items={[
                  { key: 'pending', label: 'Menunggu persetujuan', count: data?.pending_approvals?.length || 0, highlight: (data?.pending_approvals?.length || 0) > 0 },
                  { key: 'scheduled', label: 'Terjadwal', count: data?.scheduled?.length || 0 },
                ]}
              />
            }
          />
          {listFor.length === 0 ? (
            <div className="p-5">
              <EmptyState
                icon={tab === 'pending' ? ShieldCheck : CalendarClock}
                title={tab === 'pending' ? 'Tidak ada konten menunggu persetujuan' : 'Belum ada publikasi terjadwal'}
                description={tab === 'pending'
                  ? 'Konten baru akan muncul di sini setelah AI selesai membuatnya, dan tidak akan tayang sebelum Anda setujui.'
                  : 'Setujui konten dengan jadwal tertentu untuk melihatnya di sini.'}
                className="border-0 bg-transparent"
              />
            </div>
          ) : (
            <ul className="divide-y divide-line">
              {listFor.map((pub) => (
                <PublicationRow
                  key={pub.id}
                  pub={pub}
                  busy={busy}
                  onApprove={approve}
                  onCancel={cancel}
                />
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader title="Riwayat aktivitas" icon={History} description="Jejak tindakan otomatisasi terakhir." />
          {(data?.activity || []).length === 0 ? (
            <div className="p-4">
              <p className="text-xs leading-relaxed text-ink-muted">
                Belum ada aktivitas. Setiap perubahan pengaturan, persetujuan, publikasi, dan
                pembatalan akan tercatat di sini.
              </p>
            </div>
          ) : (
            <ul className="max-h-[26rem] divide-y divide-line overflow-y-auto">
              {(data?.activity || []).map((event) => {
                const tone = event.status === 'error' ? 'danger' : event.status === 'warning' ? 'warning' : 'neutral';
                return (
                  <li key={event.id} className="px-4 py-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 text-xs leading-relaxed text-ink">{truncate(event.message || event.action, 110)}</p>
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

      {onOpenRun && (
        <Alert tone="info" title="Ingin meninjau isi konten?">
          Buka <strong>Riwayat Konten</strong> untuk melihat pratinjau slide, mengedit caption, dan memeriksa
          riwayat proses AI sebelum menyetujui publikasi.
        </Alert>
      )}
    </div>
  );
}
