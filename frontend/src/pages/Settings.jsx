import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Database,
  ExternalLink,
  Info,
  KeyRound,
  RefreshCw,
  Server,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { api } from '../api';
import { Alert, Badge, Button, Card, CardHeader, Field, Input, PageHeader, Spinner } from '../components/ui';
import { fmtTime } from '../lib/format';
import { cn } from '../lib/utils';

export default function Settings({ apiKeyInput, setApiKeyInput, apiKeySet, apiKeyRequired = true, onSaveApiKey, onClearApiKey, online }) {
  const [health, setHealth] = useState(null);
  const [ops, setOps] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [healthRes, opsRes] = await Promise.all([api.getHealth(), api.getOpsStatus()]);
      setHealth(healthRes);
      setOps(opsRes);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const submitKey = (event) => {
    event.preventDefault();
    onSaveApiKey();
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2500);
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Pengaturan"
        description="Kunci akses dan status layanan. Pengaturan rahasia server tidak dapat diubah dari antarmuka."
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Kunci API"
            description={apiKeyRequired
              ? 'Dibutuhkan agar aplikasi boleh membuat konten, menyetujui, dan memposting.'
              : 'Server lokal tidak mewajibkan kunci ini. Isi hanya bila backend dijalankan dengan GTNIC_API_KEY.'}
            icon={KeyRound}
            actions={<Badge tone={apiKeySet ? 'success' : 'warning'}>{apiKeySet ? 'Tersimpan' : 'Belum diatur'}</Badge>}
          />
          <form onSubmit={submitKey} className="space-y-3 p-5">
            <Field
              label="X-API-Key"
              htmlFor="api-key"
              hint="Kunci disimpan hanya di browser ini (localStorage) dan tidak dikirim pada permintaan baca."
            >
              <Input
                id="api-key"
                type="password"
                autoComplete="off"
                spellCheck="false"
                value={apiKeyInput}
                onChange={(event) => setApiKeyInput(event.target.value)}
                placeholder="Masukkan kunci API dari admin server"
              />
            </Field>

            {saved && (
              <Alert tone="success">
                <span className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> Kunci API {apiKeyInput ? 'disimpan' : 'dihapus'}.
                </span>
              </Alert>
            )}

            <div className="flex flex-wrap gap-2">
              <Button type="submit" icon={ShieldCheck}>Simpan kunci</Button>
              <Button type="button" variant="secondary" icon={Trash2} onClick={onClearApiKey} disabled={!apiKeySet}>
                Hapus kunci
              </Button>
            </div>

            <p className="rounded-xl bg-canvas p-3 text-[11px] leading-relaxed text-ink-muted">
              Jangan bagikan kunci ini. Jika kunci bocor, minta admin menggantinya di server. Aplikasi tidak pernah
              menampilkan kembali kunci yang sudah tersimpan.
            </p>
          </form>
        </Card>

        <Card>
          <CardHeader
            title="Status layanan"
            description="Diperiksa langsung ke backend saat halaman ini dibuka."
            icon={Server}
            actions={
              <Button size="xs" variant="secondary" icon={RefreshCw} loading={loading} onClick={load}>
                Periksa
              </Button>
            }
          />
          <div className="space-y-3 p-5">
            {loading && !health ? (
              <Spinner label="Memeriksa koneksi…" />
            ) : error ? (
              <Alert tone="error" title="Backend tidak merespons">
                {error}. Pastikan server berjalan di port 8000.
              </Alert>
            ) : (
              <>
                <div className="flex items-center justify-between rounded-xl border border-line bg-canvas px-3.5 py-3">
                  <span className="text-sm text-ink">Status aplikasi</span>
                  <span className={cn('flex items-center gap-1.5 text-xs font-semibold', online ? 'text-success-700' : 'text-danger-600')}>
                    <span className={cn('h-2 w-2 rounded-full', online ? 'bg-success-500' : 'bg-danger-500')} aria-hidden="true" />
                    {online ? 'Terhubung' : 'Tidak terhubung'}
                  </span>
                </div>
                <dl className="divide-y divide-line rounded-xl border border-line">
                  {[
                    { label: 'Layanan', value: health?.service || health?.status || '-' },
                    { label: 'Versi', value: health?.version || '-' },
                    { label: 'Penjadwal', value: ops?.scheduler?.enabled ? 'Aktif' : 'Nonaktif' },
                    { label: 'Instagram', value: ops?.analytics_ingestion?.instagram_configured ? 'Terkonfigurasi' : 'Belum' },
                    { label: 'Lingkungan', value: ops?.environment || '-' },
                    { label: 'Metrik terakhir', value: ops?.analytics_ingestion?.last_real_metrics_at ? fmtTime(ops.analytics_ingestion.last_real_metrics_at) : 'Belum ada' },
                  ].map((row) => (
                    <div key={row.label} className="flex items-center justify-between gap-3 px-3.5 py-2.5 text-xs">
                      <dt className="text-ink-muted">{row.label}</dt>
                      <dd className="truncate font-medium text-ink">{row.value}</dd>
                    </div>
                  ))}
                </dl>
                <a
                  href="/docs"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-700 hover:underline"
                >
                  Buka dokumentasi API <ExternalLink className="h-3 w-3" aria-hidden="true" />
                </a>
              </>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Data & privasi" icon={Database} />
          <div className="space-y-3 p-5 text-sm text-ink-muted">
            <p className="leading-relaxed">
              Aplikasi menyimpan tiga hal di browser Anda: kunci API, id konten terakhir yang dibuka, dan preferensi
              tampilan. Tidak ada data pelanggan yang disimpan di browser.
            </p>
            <Button
              size="sm"
              variant="secondary"
              icon={Trash2}
              onClick={() => {
                try {
                  window.localStorage.removeItem('agent-sosmed:last-run-id');
                } catch {
                  /* localStorage diblokir */
                }
              }}
            >
              Hapus memori konten terakhir
            </Button>
            <div className="rounded-xl bg-canvas p-3 text-[11px] leading-relaxed">
              Semua konten, aset, dan metrik tersimpan di server. Menghapus data browser tidak menghapus data konten.
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Tentang aplikasi" icon={Info} />
          <div className="space-y-3 p-5 text-sm text-ink-muted">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                <Info className="h-5 w-5" aria-hidden="true" />
              </span>
              <div>
                <p className="font-semibold text-ink">GTNIC — Asisten Pemasaran AI untuk UMKM</p>
                <p className="mt-0.5 text-xs leading-relaxed">
                  Membantu membuat carousel dan video Reels, menyusun kalender konten, memposting ke Instagram, dan
                  membaca performanya.
                </p>
              </div>
            </div>
            <ul className="space-y-1 text-xs">
              <li>• Antarmuka: React + Vite + Tailwind CSS</li>
              <li>• Backend: FastAPI (tidak diubah oleh pembaruan ini)</li>
              <li>• AI: pipeline multi-agen untuk riset, desain, dan video</li>
            </ul>
            <p className="text-[11px] leading-relaxed text-ink-subtle">
              GTNIC 2026 · AI Agents for Enterprise Productivity
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
}
