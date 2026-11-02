import { useCallback, useEffect, useRef, useState } from 'react';
import { Bell, CheckCheck, Loader2, Megaphone } from 'lucide-react';
import { api } from '../api';
import { cn } from '../lib/utils';
import { timeAgo } from '../lib/format';
import { EmptyState } from './ui';

const SEVERITY_STYLE = {
  error: 'bg-danger-500',
  warning: 'bg-warning-500',
  success: 'bg-success-500',
  info: 'bg-brand-400',
};

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const panelRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getNotifications({ limit: 12 });
      setItems(res.items || []);
      setUnread(res.unread || 0);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!open) return undefined;
    const onClick = (event) => {
      if (panelRef.current && !panelRef.current.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const markRead = async (id) => {
    try {
      await api.readNotification(id);
      setItems((list) => list.map((item) => (item.id === id ? { ...item, is_read: true } : item)));
      setUnread((count) => Math.max(0, count - 1));
    } catch (err) {
      setError(err.message);
    }
  };

  const markAll = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.readAllNotifications();
      setItems((list) => list.map((item) => ({ ...item, is_read: true })));
      setUnread(0);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => {
          setOpen((value) => !value);
          if (!open) load();
        }}
        aria-label={unread > 0 ? `Notifikasi, ${unread} belum dibaca` : 'Notifikasi'}
        aria-expanded={open}
        className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-line bg-surface text-ink-muted transition hover:bg-soft hover:text-ink"
      >
        <Bell className="h-5 w-5" aria-hidden="true" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-danger-500 px-1 text-[10px] font-bold text-white ring-2 ring-surface">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="fixed inset-x-3 top-[4.5rem] z-[70] overflow-hidden rounded-2xl border border-line bg-surface shadow-popover animate-slide-up sm:absolute sm:inset-x-auto sm:right-0 sm:top-12 sm:w-[22rem]">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <div className="flex items-center gap-2">
              <Megaphone className="h-4 w-4 text-brand-600" aria-hidden="true" />
              <p className="text-sm font-semibold text-ink">Notifikasi</p>
            </div>
            <button
              type="button"
              onClick={markAll}
              disabled={busy || unread === 0}
              className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-semibold text-brand-700 transition hover:bg-brand-50 disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCheck className="h-3.5 w-3.5" />}
              Tandai semua
            </button>
          </div>

          <div className="max-h-[min(60vh,22rem)] overflow-y-auto">
            {loading && items.length === 0 ? (
              <div className="flex items-center justify-center gap-2 py-10 text-sm text-ink-muted">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Memuat notifikasi…
              </div>
            ) : error ? (
              <div className="px-4 py-6 text-sm text-danger-600">
                {error}
                <button type="button" onClick={load} className="ml-2 font-semibold underline">
                  Coba lagi
                </button>
              </div>
            ) : items.length === 0 ? (
              <EmptyState
                icon={Bell}
                title="Belum ada notifikasi"
                description="Kabar penting soal proses konten dan publikasi akan muncul di sini."
                className="border-0 bg-transparent py-8"
              />
            ) : (
              <ul className="divide-y divide-line">
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => !item.is_read && markRead(item.id)}
                      className={cn(
                        'flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-canvas',
                        !item.is_read && 'bg-brand-50/40'
                      )}
                    >
                      <span
                        className={cn(
                          'mt-1.5 h-2 w-2 shrink-0 rounded-full',
                          item.is_read ? 'bg-line' : SEVERITY_STYLE[item.severity] || 'bg-brand-400'
                        )}
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-ink">{item.title}</span>
                        <span className="mt-0.5 block text-xs leading-relaxed text-ink-muted">{item.message}</span>
                        <span className="mt-1 block text-[11px] text-ink-subtle">{timeAgo(item.created_at)}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="border-t border-line bg-canvas px-4 py-2 text-[11px] text-ink-muted">
            Notifikasi dibuat otomatis oleh backend setiap ada kejadian penting.
          </div>
        </div>
      )}
    </div>
  );
}
