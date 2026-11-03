import {
  AlertCircle,
  ArrowRight,
  Film,
  KeyRound,
  Layers,
  Lightbulb,
  Plus,
  Search,
  Sparkles,
  Wand2,
} from 'lucide-react';
import { Alert, Badge, Button, Card, CardHeader, Field, PageHeader, Switch } from '../components/ui';
import ContentPreview from '../components/ContentPreview';
import ActivityFeed from '../components/ActivityFeed';
import { cn } from '../lib/utils';
import { fmtTime, runStatusMeta } from '../lib/format';

const EXAMPLE_TOPICS = [
  '5 cara mengatur cashflow usaha kecil saat harga bahan naik',
  'Tips memilih kemasan produk agar tahan lama dan terlihat premium',
  'Cara meningkatkan repeat order lewat layanan pelanggan',
  'Kesalahan umum UMKM saat memotret produk dengan HP',
  'Strategi promo akhir bulan tanpa merusak margin',
];

const FORMATS = [
  {
    key: 'carousel',
    title: 'Carousel Instagram',
    ratio: '4:5 · 1080×1350',
    description: '5–8 slide berisi penjelasan bertahap. Cocok untuk edukasi, tips, dan perbandingan.',
    icon: Layers,
  },
  {
    key: 'video',
    title: 'Video Reels',
    ratio: '9:16 · 1080×1920',
    description: 'Video pendek dengan naskah dan suara otomatis. Cocok untuk menarik audiens baru.',
    icon: Film,
  },
];

export default function Generator({
  topic,
  setTopic,
  formatType,
  setFormatType,
  targetDuration,
  setTargetDuration,
  freshResearch,
  setFreshResearch,
  isRunning,
  runData,
  events,
  currentRunId,
  onSubmit,
  onReset,
  onPublish,
  publishing,
  publishResult,
  videoCaption,
  setVideoCaption,
  shareToFeed,
  setShareToFeed,
  currentSlideIndex,
  setCurrentSlideIndex,
  pendingItems,
  pendingLeft,
  approvingAssetId,
  regeneratingId,
  resumingRun,
  onApprove,
  onRegenerate,
  onResume,
  apiKeySet,
  apiKeyRequired = true,
  onOpenSettings,
}) {
  const isVideoRun = (runData?.format ?? formatType) === 'video';
  const keyMissing = apiKeyRequired && !apiKeySet;
  const slides = runData?.design?.slides || [];
  const video = runData?.video || null;
  const runFailed = runData?.status === 'failed';
  const statusMeta = runData ? runStatusMeta(runData.status) : null;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Buat konten dengan AI"
        description="Tulis satu topik, lalu AI menyiapkan riset, desain, dan caption. Anda tetap memutuskan sebelum konten diposting."
        actions={
          <>
            {statusMeta && (
              <span className={`badge badge-${statusMeta.tone === 'neutral' ? 'neutral' : statusMeta.tone}`}>{statusMeta.label}</span>
            )}
            {runData && (
              <Button variant="secondary" size="sm" icon={Plus} onClick={onReset}>
                Konten baru
              </Button>
            )}
          </>
        }
      />

      {/* Langkah singkat */}
      {!runData && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[
            { icon: Lightbulb, title: '1. Tulis topik', text: 'Cukup satu kalimat tentang hal yang ingin Anda bagikan.' },
            { icon: Wand2, title: '2. AI menyiapkan', text: 'Riset fakta, susun alur, lalu desain slide atau video.' },
            { icon: Sparkles, title: '3. Periksa & posting', text: 'Setujui hasilnya, lalu posting ke Instagram dari sini.' },
          ].map((step) => (
            <div key={step.title} className="flex items-start gap-3 rounded-xl border border-line bg-surface p-3.5 shadow-card">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                <step.icon className="h-4.5 w-4.5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-ink">{step.title}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{step.text}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Form */}
      <Card>
        <CardHeader
          title="Detail konten"
          description="Semakin spesifik topiknya, semakin relevan hasil yang dibuat AI."
          icon={Sparkles}
        />
        <form onSubmit={onSubmit} className="space-y-5 p-5">
          <Field
            label="Topik konten"
            htmlFor="topic"
            required
            hint="Contoh gaya penulisan: angka + manfaat + target pembaca. Hindari topik yang terlalu umum."
          >
            <textarea
              id="topic"
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder="Contoh: 5 cara mengatur cashflow usaha kecil saat harga bahan naik"
              rows={3}
              maxLength={300}
              disabled={isRunning}
              className="input"
              required
            />
            <div className="mt-1 flex items-center justify-between text-[11px] text-ink-subtle">
              <span>{topic.trim().length} karakter</span>
              <span>Maksimal 300 karakter</span>
            </div>
          </Field>

          <div>
            <p className="mb-1.5 text-sm font-medium text-ink">Ide cepat</p>
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLE_TOPICS.map((example) => (
                <button
                  key={example}
                  type="button"
                  disabled={isRunning}
                  onClick={() => setTopic(example)}
                  className="rounded-full border border-line bg-canvas px-3 py-1.5 text-xs text-ink-muted transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800 disabled:opacity-50"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-1.5 text-sm font-medium text-ink">Format konten</p>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {FORMATS.map((format) => {
                const active = formatType === format.key;
                const Icon = format.icon;
                return (
                  <button
                    key={format.key}
                    type="button"
                    onClick={() => setFormatType(format.key)}
                    disabled={isRunning}
                    aria-pressed={active}
                    className={cn(
                      'flex items-start gap-3 rounded-xl border p-3.5 text-left transition disabled:opacity-60',
                      active ? 'border-brand-400 bg-brand-50 ring-2 ring-brand-400/20' : 'border-line bg-surface hover:border-brand-200'
                    )}
                  >
                    <span
                      className={cn(
                        'flex h-9 w-9 shrink-0 items-center justify-center rounded-xl',
                        active ? 'bg-brand-400 text-[#08303f]' : 'bg-canvas text-ink-muted'
                      )}
                    >
                      <Icon className="h-4.5 w-4.5" aria-hidden="true" />
                    </span>
                    <span className="min-w-0">
                      <span className="flex items-center gap-1.5">
                        <span className="text-sm font-semibold text-ink">{format.title}</span>
                        {active && <Badge tone="brand" className="text-[10px]">Dipilih</Badge>}
                      </span>
                      <span className="mt-0.5 block text-[11px] font-medium text-ink-subtle">{format.ratio}</span>
                      <span className="mt-1 block text-xs leading-relaxed text-ink-muted">{format.description}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 border-t border-line pt-4 sm:grid-cols-2">
            <div className="rounded-xl bg-canvas p-3.5">
              <Switch
                checked={freshResearch}
                onChange={setFreshResearch}
                disabled={isRunning}
                label="Riset fakta terbaru"
                description={
                  formatType === 'video'
                    ? 'Aktif: AI mencari fakta baru di web. Nonaktif: memakai riset tersimpan (24 jam) untuk topik yang sama.'
                    : 'Aktif: AI mencari data dan tren terbaru di web sebelum menulis.'
                }
              />
            </div>

            {formatType === 'video' ? (
              <Field label="Target durasi video" htmlFor="duration" hint="Durasi lebih pendek lebih cepat selesai diproses.">
                <select
                  id="duration"
                  value={targetDuration}
                  onChange={(event) => setTargetDuration(Number(event.target.value))}
                  disabled={isRunning}
                  className="input cursor-pointer"
                >
                  <option value={15}>15 detik</option>
                  <option value={30}>30 detik (standar)</option>
                  <option value={60}>60 detik</option>
                </select>
              </Field>
            ) : (
              <div className="flex items-start gap-2 rounded-xl bg-canvas p-3.5 text-xs leading-relaxed text-ink-muted">
                <Search className="mt-0.5 h-4 w-4 shrink-0 text-brand-500" aria-hidden="true" />
                <p>
                  AI akan mencari sumber, menyusun alur slide, lalu merender gambar. Proses biasanya 1–3 menit
                  dan berjalan di server, jadi Anda boleh menutup halaman.
                </p>
              </div>
            )}
          </div>

          {keyMissing && (
            <Alert tone="warning" title="Kunci API belum diatur" action={
              <Button size="xs" variant="secondary" icon={KeyRound} onClick={onOpenSettings}>
                Buka pengaturan
              </Button>
            }>
              Aksi membuat konten memerlukan kunci API yang tersimpan di browser ini.
            </Alert>
          )}

          <div className="flex flex-col gap-2 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="order-2 text-xs leading-relaxed text-ink-muted sm:order-1">
              {formatType === 'video'
                ? 'Hasil: 1 video Reels + caption yang bisa Anda edit sebelum posting.'
                : 'Hasil: carousel beberapa slide + caption Instagram siap posting.'}
            </p>
            <Button
              type="submit"
              size="lg"
              icon={isRunning ? undefined : Sparkles}
              loading={isRunning}
              disabled={isRunning || !topic.trim()}
              className="order-1 w-full sm:order-2 sm:w-auto"
            >
              {isRunning ? 'AI sedang bekerja…' : 'Buat konten sekarang'}
            </Button>
          </div>
        </form>
      </Card>

      {/* Ruang kerja */}
      {(runData || currentRunId || isRunning) && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
          <div className="xl:col-span-7">
            <ContentPreview
              runData={runData}
              isVideoRun={isVideoRun}
              runFailed={runFailed}
              slides={slides}
              video={video}
              currentSlideIndex={currentSlideIndex}
              setCurrentSlideIndex={setCurrentSlideIndex}
              publishing={publishing}
              publishResult={publishResult}
              videoCaption={videoCaption}
              setVideoCaption={setVideoCaption}
              shareToFeed={shareToFeed}
              setShareToFeed={setShareToFeed}
              pendingItems={pendingItems}
              pendingLeft={pendingLeft}
              approvingAssetId={approvingAssetId}
              regeneratingId={regeneratingId}
              resumingRun={resumingRun}
              onApprove={onApprove}
              onRegenerate={onRegenerate}
              onResume={onResume}
              onPublish={onPublish}
            />
          </div>
          <div className="xl:col-span-5">
            <ActivityFeed events={events} isRunning={isRunning} status={runData?.status} />
            {runData?.started_at && (
              <p className="mt-2 text-right text-[11px] text-ink-subtle">
                Dimulai {fmtTime(runData.started_at)}
                {runData.finished_at ? ` · selesai ${fmtTime(runData.finished_at)}` : ''}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Tips saat belum ada run */}
      {!runData && !isRunning && (
        <Card className="p-5">
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-warning-50 text-warning-600">
              <AlertCircle className="h-4.5 w-4.5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">Agar hasilnya lebih bagus</p>
              <ul className="mt-1.5 space-y-1 text-sm leading-relaxed text-ink-muted">
                <li className="flex gap-2"><ArrowRight className="mt-1 h-3.5 w-3.5 shrink-0 text-brand-500" aria-hidden="true" /> Sebutkan target pembaca, misalnya “untuk pemilik warung kopi”.</li>
                <li className="flex gap-2"><ArrowRight className="mt-1 h-3.5 w-3.5 shrink-0 text-brand-500" aria-hidden="true" /> Sebutkan tujuan konten: edukasi, promo, atau pengumuman.</li>
                <li className="flex gap-2"><ArrowRight className="mt-1 h-3.5 w-3.5 shrink-0 text-brand-500" aria-hidden="true" /> Hindari klaim berlebihan seperti “pasti untung 10x” agar tidak melanggar aturan brand Anda.</li>
              </ul>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
