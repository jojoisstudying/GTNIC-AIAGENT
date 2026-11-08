import { useState } from 'react';
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  Film,
  Image as ImageIcon,
  Layers,
  Loader2,
  RefreshCw,
  Send,
  Sparkles,
} from 'lucide-react';
import { Alert, Badge, Button, Card, EmptyState, Modal, ProgressBar, StatusBadge } from './ui';
import { cn } from '../lib/utils';
import { fmtMoney, publicationMeta, runErrorHint, runStatusMeta } from '../lib/format';
import { mediaUrl } from '../api';

function PoseReview({ items, approvingAssetId, regeneratingId, resumingRun, pendingLeft, onApprove, onRegenerate, onResume }) {
  return (
    <div className="rounded-xl border border-warning-100 bg-warning-50/70 p-3.5">
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4.5 w-4.5 shrink-0 text-warning-600" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-warning-700">Perlu persetujuan Anda</p>
          <p className="mt-0.5 text-xs leading-relaxed text-warning-700/90">
            AI sudah membuat pose dari foto model Anda. Setujui pose yang cocok agar slide final bisa dirakit.
            Tolak pose yang aneh, lalu buat ulang.
          </p>
        </div>
      </div>

      <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
        {items.map((item) => {
          const status = item.status || 'pending_review';
          const busy = approvingAssetId === item.id || regeneratingId === item.id || resumingRun;
          return (
            <li key={item.id} className="rounded-xl border border-line bg-surface p-2.5">
              <div className="flex items-center gap-2.5">
                <span className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-line bg-canvas">
                  {item.url ? (
                    <img src={mediaUrl(item.url)} alt={`Pose ${item.pose}`} className="h-full w-full object-contain" loading="lazy" />
                  ) : (
                    <ImageIcon className="h-5 w-5 text-ink-subtle" aria-hidden="true" />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-ink">Pose: {item.pose}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1">
                    <Badge tone={item.qc?.ok ? 'success' : 'danger'} className="text-[10px]">
                      {item.qc?.ok ? 'Kualitas OK' : 'Kualitas bermasalah'}
                    </Badge>
                    {status !== 'pending_review' && (
                      <Badge tone={status === 'approved' ? 'success' : status === 'rejected' ? 'danger' : 'neutral'} className="text-[10px]">
                        {status === 'approved' ? 'Disetujui' : status === 'rejected' ? 'Ditolak' : status}
                      </Badge>
                    )}
                  </div>
                </div>
              </div>

              <div className="mt-2 flex items-center gap-1.5">
                {status === 'pending_review' ? (
                  <>
                    <Button
                      size="xs"
                      variant="success"
                      icon={Check}
                      loading={approvingAssetId === item.id}
                      disabled={busy}
                      onClick={() => onApprove(item.id, 'approved')}
                      className="flex-1"
                    >
                      Setujui
                    </Button>
                    <Button
                      size="xs"
                      variant="secondary"
                      disabled={busy}
                      onClick={() => onApprove(item.id, 'rejected')}
                      className="flex-1"
                    >
                      Tolak
                    </Button>
                  </>
                ) : (
                  status === 'rejected' && (
                    <Button
                      size="xs"
                      variant="secondary"
                      icon={RefreshCw}
                      loading={regeneratingId === item.id}
                      disabled={busy}
                      onClick={() => onRegenerate(item.id)}
                    >
                      Buat ulang pose
                    </Button>
                  )
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[11px] leading-relaxed text-warning-700/90">
          {pendingLeft ? 'Masih ada pose yang belum diputuskan.' : 'Semua pose sudah diputuskan. Lanjutkan untuk merender slide final.'}
        </p>
        <Button
          size="sm"
          variant="warning"
          icon={resumingRun ? undefined : Sparkles}
          loading={resumingRun}
          disabled={pendingLeft}
          onClick={onResume}
          title={pendingLeft ? 'Putuskan semua pose terlebih dahulu' : undefined}
        >
          Lanjutkan proses
        </Button>
      </div>
    </div>
  );
}

export default function ContentPreview({
  runData,
  isVideoRun,
  runFailed,
  slides = [],
  video,
  currentSlideIndex,
  setCurrentSlideIndex,
  publishing,
  publishResult,
  videoCaption,
  setVideoCaption,
  shareToFeed,
  setShareToFeed,
  pendingItems = [],
  pendingLeft,
  approvingAssetId,
  regeneratingId,
  resumingRun,
  onApprove,
  onRegenerate,
  onResume,
  onPublish,
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);

  const plan = runData?.plan;
  const isReel = isVideoRun && runData && !plan;
  const captionTooLong = videoCaption.length > 2200;
  const reelPub = publishResult?.format === 'reel' ? publishResult : runData?.publication;
  const reelPublished = reelPub?.status === 'published';
  const carouselPub = publishResult || runData?.publication;
  const carouselPublished = carouselPub?.status === 'published';

  // Siap diposting: status 'ok', atau 'awaiting_approval' tanpa pose yang menunggu review.
  // Gerbang sebenarnya (QC, persetujuan item kalender, pose pending) ditegakkan backend.
  const readyToPublish =
    runData?.status === 'ok' || (runData?.status === 'awaiting_approval' && pendingItems.length === 0);
  const canPublishReel =
    readyToPublish && video?.ok && !reelPublished && videoCaption.trim().length > 0 && !captionTooLong && !publishing;
  const canPublishCarousel = readyToPublish && !carouselPublished && !publishing;

  const pubMeta = publicationMeta(carouselPub?.status);
  const statusMeta = runData ? runStatusMeta(runData.status) : null;

  const slide = slides[currentSlideIndex];
  const progressPct = readyToPublish ? 100 : runData?.status === 'running' ? 65 : 30;

  return (
    <Card className="flex flex-col overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-brand-600" aria-hidden="true" />
          <p className="text-sm font-semibold text-ink">Pratinjau konten</p>
          <Badge tone="neutral" className="bg-canvas">
            {isVideoRun ? 'Reels' : 'Carousel'}
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          {runData && statusMeta && <StatusBadge meta={statusMeta} dot />}
        </div>
      </div>

      <div className="flex-1 space-y-3 p-4">
        {runData?.status === 'running' && (
          <div className="rounded-xl border border-brand-200 bg-brand-50 p-3.5">
            <div className="flex items-center gap-2 text-sm font-semibold text-brand-800">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              AI sedang bekerja…
            </div>
            <p className="mt-1 text-xs leading-relaxed text-brand-800/80">
              Proses biasanya membutuhkan 1–3 menit. Anda boleh meninggalkan halaman ini; proses tetap berjalan di server.
            </p>
            <ProgressBar value={progressPct} className="mt-2.5" />
          </div>
        )}

        {runData?.status === 'awaiting_approval' && pendingItems.length > 0 && (
          <PoseReview
            items={pendingItems}
            approvingAssetId={approvingAssetId}
            regeneratingId={regeneratingId}
            resumingRun={resumingRun}
            pendingLeft={pendingLeft}
            onApprove={(id, decision) => onApprove(id, decision, runData?.run_id)}
            onRegenerate={(id) => onRegenerate(id, runData?.run_id)}
            onResume={onResume}
          />
        )}

        {runData?.status === 'awaiting_assets' && (
          <Alert tone="warning" title="Foto pose belum tersedia">
            <p>
              Slide dirender tanpa foto untuk pose:{' '}
              <strong>{(runData.design?.missing_poses || []).join(', ') || '-'}</strong>. Anda bisa melanjutkan
              proses untuk mencoba membuat pose baru.
            </p>
            {runData.error && <p className="mt-1 break-words text-xs opacity-80">{runData.error}</p>}
            <Button size="xs" variant="warning" className="mt-2" loading={resumingRun} onClick={onResume}>
              Lanjutkan proses
            </Button>
          </Alert>
        )}

        {runFailed && (
          <Alert tone="error" title={isVideoRun ? 'Pembuatan video gagal' : 'Pembuatan konten gagal'}>
            <p className="break-words">
              {runData?.error || video?.issues?.join('; ') || 'Terjadi kesalahan. Lihat panel proses AI untuk detailnya.'}
            </p>
            {runErrorHint(runData?.error) && (
              <p className="mt-1.5 break-words text-xs font-medium">{runErrorHint(runData?.error)}</p>
            )}
          </Alert>
        )}

        {/* Media hasil */}
        <div className={cn('flex flex-col items-center justify-center rounded-xl bg-canvas p-3', !video?.url && slides.length === 0 && 'min-h-[18rem]')}>
          {video?.url ? (
            <div className="w-full max-w-[300px] space-y-2">
              <div className="relative w-full overflow-hidden rounded-xl border border-line bg-black shadow-card" style={{ aspectRatio: '9 / 16' }}>
                <video key={video.url} src={mediaUrl(video.url)} controls playsInline loop preload="metadata" className="h-full w-full object-contain">
                  Browser Anda tidak mendukung pemutar video.
                </video>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted">
                <span className="inline-flex items-center gap-1.5">
                  <Film className="h-3.5 w-3.5" aria-hidden="true" />
                  {video.scenes_count} scene · {Number(video.duration_sec || 0).toFixed(1)} dtk · {Number(video.file_size_mb || 0).toFixed(2)} MB
                </span>
                <a href={mediaUrl(video.url)} download className="inline-flex items-center gap-1 font-semibold text-brand-700 hover:underline">
                  <Download className="h-3.5 w-3.5" aria-hidden="true" /> Unduh MP4
                </a>
              </div>
              {video.issues?.length > 0 && (
                <ul className="space-y-1 rounded-lg border border-warning-100 bg-warning-50 p-2 text-[11px] leading-relaxed text-warning-700">
                  {video.issues.map((issue, i) => (
                    <li key={i}>• {issue}</li>
                  ))}
                </ul>
              )}
            </div>
          ) : slides.length > 0 ? (
            <div className="w-full max-w-[360px] space-y-2.5">
              <div className="relative w-full overflow-hidden rounded-xl border border-line bg-white shadow-card" style={{ aspectRatio: '4 / 5' }}>
                <img
                  src={mediaUrl(slide?.image_url)}
                  alt={`Slide ${currentSlideIndex + 1} dari ${slides.length}`}
                  className="h-full w-full object-contain"
                />
                <span className="absolute right-2 top-2 rounded-md bg-[#243447]/80 px-2 py-0.5 text-[11px] font-medium text-white">
                  {currentSlideIndex + 1} / {slides.length}
                </span>
              </div>

              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => setCurrentSlideIndex(Math.max(0, currentSlideIndex - 1))}
                  disabled={currentSlideIndex === 0}
                  aria-label="Slide sebelumnya"
                  className="btn-icon disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                </button>
                <span className="text-xs text-ink-muted">Slide {currentSlideIndex + 1} dari {slides.length}</span>
                <button
                  type="button"
                  onClick={() => setCurrentSlideIndex(Math.min(slides.length - 1, currentSlideIndex + 1))}
                  disabled={currentSlideIndex === slides.length - 1}
                  aria-label="Slide berikutnya"
                  className="btn-icon disabled:opacity-40"
                >
                  <ChevronRight className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>

              <div className="no-scrollbar flex gap-1.5 overflow-x-auto pb-1">
                {slides.map((item, index) => (
                  <button
                    key={item.image_url || index}
                    type="button"
                    onClick={() => setCurrentSlideIndex(index)}
                    aria-label={`Lihat slide ${index + 1}`}
                    aria-current={index === currentSlideIndex}
                    className={cn(
                      'h-14 w-11 shrink-0 overflow-hidden rounded-md border-2 bg-white transition',
                      index === currentSlideIndex ? 'border-brand-400' : 'border-transparent hover:border-brand-200'
                    )}
                  >
                    <img src={mediaUrl(item.image_url)} alt="" className="h-full w-full object-cover" loading="lazy" />
                  </button>
                ))}
              </div>
            </div>
          ) : runData?.status === 'running' ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <Loader2 className="h-7 w-7 animate-spin text-brand-500" aria-hidden="true" />
              <p className="text-sm font-medium text-ink">
                {isVideoRun ? 'Menyiapkan naskah, suara, dan video…' : 'Menyiapkan riset dan desain slide…'}
              </p>
              <p className="max-w-xs text-xs leading-relaxed text-ink-muted">
                Hasil akan muncul otomatis di sini. Tidak perlu menyegarkan halaman.
              </p>
            </div>
          ) : runFailed ? (
            <p className="py-6 text-xs text-ink-muted">Tidak ada hasil untuk ditampilkan karena proses gagal.</p>
          ) : (
            <EmptyState
              icon={isVideoRun ? Film : Layers}
              title="Belum ada konten untuk ditampilkan"
              description='Tulis topik di formulir, lalu tekan "Buat konten". Hasil AI akan muncul di sini untuk Anda periksa.'
              className="border-0 bg-transparent"
            />
          )}
        </div>

        {/* Caption Reels */}
        {isReel && video?.ok && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label htmlFor="reel-caption" className="text-sm font-medium text-ink">
                Caption untuk Reels
              </label>
              <span className={cn('text-[11px]', captionTooLong ? 'font-semibold text-danger-600' : 'text-ink-muted')}>
                {videoCaption.length}/2200
              </span>
            </div>
            <textarea
              id="reel-caption"
              value={videoCaption}
              onChange={(event) => setVideoCaption(event.target.value)}
              disabled={reelPublished || publishing}
              rows={4}
              placeholder="Tulis caption + hashtag (maksimal 30 hashtag)…"
              className="input text-sm disabled:opacity-60"
            />
            <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-muted">
              <input
                type="checkbox"
                checked={shareToFeed}
                disabled={reelPublished || publishing}
                onChange={(event) => setShareToFeed(event.target.checked)}
                className="h-4 w-4 rounded border-line accent-brand-500"
              />
              Tampilkan juga di feed profil Instagram
            </label>
          </div>
        )}

        {/* Caption Carousel */}
        {plan && (
          <div>
            <p className="mb-1.5 text-sm font-medium text-ink">Draf caption Instagram</p>
            <div className="max-h-28 overflow-y-auto rounded-xl border border-line bg-canvas p-3 text-xs leading-relaxed text-ink-muted">
              {plan.caption || 'Belum ada caption dari AI.'}
            </div>
          </div>
        )}

        {/* Status publikasi */}
        {isReel && reelPub && (
          <Alert tone={reelPublished ? 'success' : reelPub.status === 'intent' ? 'warning' : 'error'}>
            <p className="font-semibold">
              {reelPublished
                ? 'Reels sudah diposting ke Instagram'
                : reelPub.status === 'intent'
                  ? 'Posting belum selesai — periksa manual sebelum mencoba lagi'
                  : 'Publikasi gagal'}
            </p>
            {reelPub.permalink && (
              <a href={reelPub.permalink} target="_blank" rel="noreferrer" className="mt-1 block font-semibold underline">
                Lihat Reels di Instagram →
              </a>
            )}
            {reelPub.error && <p className="mt-1 break-words text-xs">{reelPub.error}</p>}
          </Alert>
        )}

        {!isReel && carouselPub && (
          <Alert tone={carouselPublished ? 'success' : pubMeta.tone === 'warning' ? 'warning' : 'error'}>
            <p className="font-semibold">{pubMeta.label}</p>
            {carouselPub.permalink && (
              <a href={carouselPub.permalink} target="_blank" rel="noreferrer" className="mt-1 block font-semibold underline">
                Lihat postingan di Instagram →
              </a>
            )}
            {carouselPub.error && <p className="mt-1 break-words text-xs">{carouselPub.error}</p>}
          </Alert>
        )}
      </div>

      {/* Action bar */}
      {runData && (
        <div className="border-t border-line bg-canvas px-4 py-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-ink-muted">
              Biaya proses: <strong className="font-semibold text-ink">{fmtMoney(runData.cost_usd)}</strong>
              <span className="mx-1.5 text-ink-subtle">·</span>
              {((runData.tokens_in || 0) + (runData.tokens_out || 0)).toLocaleString('id-ID')} token
            </p>
            {isReel ? (
              <Button
                icon={Send}
                loading={publishing}
                disabled={!canPublishReel || reelPublished}
                onClick={() => setConfirmOpen(true)}
                title={
                  reelPublished
                    ? 'Reels sudah diposting'
                    : !video?.ok
                      ? 'Video belum siap'
                      : captionTooLong
                        ? 'Caption melebihi 2200 karakter'
                        : undefined
                }
              >
                {reelPublished ? 'Sudah diposting' : publishing ? 'Memposting…' : 'Posting Reels ke Instagram'}
              </Button>
            ) : (
              <Button
                icon={Send}
                loading={publishing}
                disabled={!canPublishCarousel}
                onClick={() => setConfirmOpen(true)}
                title={
                  carouselPublished
                    ? 'Konten ini sudah diposting'
                    : !readyToPublish
                      ? 'Konten harus selesai diproses terlebih dahulu'
                      : undefined
                }
              >
                {carouselPublished ? 'Sudah diposting' : publishing ? 'Memposting…' : 'Posting ke Instagram'}
              </Button>
            )}
          </div>
          {!isReel && readyToPublish && !carouselPublished && (
            <p className="mt-1.5 text-[11px] text-ink-muted">
              Caption yang dipakai adalah draf di atas. Periksa kembali sebelum memposting.
            </p>
          )}
        </div>
      )}

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Posting ke Instagram sekarang?"
        description={`Konten ${isVideoRun ? 'Reels' : 'carousel'} ini akan langsung tayang di akun Instagram yang terhubung. Tindakan ini tidak bisa dibatalkan dari aplikasi.`}
        icon={Send}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmOpen(false)}>
              Batal
            </Button>
            <Button
              icon={CheckCircle2}
              onClick={() => {
                setConfirmOpen(false);
                onPublish();
              }}
            >
              Ya, posting sekarang
            </Button>
          </>
        }
      >
        <div className="space-y-2 rounded-xl bg-canvas p-3 text-xs leading-relaxed text-ink-muted">
          <p><strong className="text-ink">Format:</strong> {isVideoRun ? 'Video Reels (9:16)' : 'Carousel Instagram'}</p>
          {isVideoRun && <p className="line-clamp-2"><strong className="text-ink">Caption:</strong> {videoCaption}</p>}
        </div>
      </Modal>
    </Card>
  );
}
