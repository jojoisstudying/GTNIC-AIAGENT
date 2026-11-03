import { KeyRound, Menu } from 'lucide-react';
import NotificationBell from './NotificationBell';
import { cn } from '../lib/utils';

export default function Topbar({ meta, onMenu, brandName, apiKeySet, apiKeyRequired = true, onOpenSettings }) {
  const initial = (brandName || 'GT').trim().slice(0, 2).toUpperCase();
  const keyOk = apiKeySet || !apiKeyRequired;

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onMenu}
          aria-label="Buka menu navigasi"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-line text-ink-muted transition hover:bg-soft hover:text-ink lg:hidden"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>

        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ink sm:text-base">{meta?.title || 'Dashboard'}</p>
          <p className="hidden truncate text-xs text-ink-muted sm:block">
            {meta?.description || 'Asisten pemasaran AI untuk usaha Anda'}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onOpenSettings}
            className={cn(
              'hidden items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition sm:inline-flex',
              keyOk
                ? 'border-success-100 bg-success-50 text-success-700 hover:bg-success-100/70'
                : 'border-warning-100 bg-warning-50 text-warning-700 hover:bg-warning-100/70'
            )}
            title={keyOk ? 'Aksi yang mengubah data diizinkan server' : 'Kunci API belum diatur — aksi yang mengubah data akan gagal'}
          >
            <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
            {keyOk ? 'API tersambung' : 'API belum diatur'}
          </button>

          <NotificationBell />

          <button
            type="button"
            onClick={onOpenSettings}
            aria-label="Buka pengaturan akun dan brand"
            className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-50 text-xs font-bold text-brand-800 ring-1 ring-brand-200 transition hover:bg-brand-100"
          >
            {initial}
          </button>
        </div>
      </div>
    </header>
  );
}
