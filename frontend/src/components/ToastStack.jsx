import { createPortal } from 'react-dom';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';
import { cn } from '../lib/utils';

const TOAST_STYLE = {
  success: { icon: CheckCircle2, ring: 'border-success-100', iconColor: 'text-success-600', bg: 'bg-white' },
  error: { icon: AlertCircle, ring: 'border-danger-100', iconColor: 'text-danger-600', bg: 'bg-white' },
  warning: { icon: AlertCircle, ring: 'border-warning-100', iconColor: 'text-warning-600', bg: 'bg-white' },
  info: { icon: Info, ring: 'border-brand-200', iconColor: 'text-brand-600', bg: 'bg-white' },
};

export default function ToastStack({ toasts, onDismiss }) {
  if (!toasts.length) return null;

  return createPortal(
    <div
      className="pointer-events-none fixed inset-x-3 bottom-4 z-[90] flex flex-col items-stretch gap-2 sm:inset-x-auto sm:right-5 sm:bottom-5 sm:w-[23rem]"
      role="region"
      aria-label="Pemberitahuan"
    >
      {toasts.map((toast) => {
        const config = TOAST_STYLE[toast.type] || TOAST_STYLE.info;
        const Icon = config.icon;
        return (
          <div
            key={toast.id}
            className={cn(
              'pointer-events-auto flex items-start gap-3 rounded-xl border p-3.5 shadow-popover animate-slide-up',
              config.ring,
              config.bg
            )}
            role={toast.type === 'error' ? 'alert' : 'status'}
          >
            <Icon className={cn('mt-0.5 h-5 w-5 shrink-0', config.iconColor)} aria-hidden="true" />
            <div className="min-w-0 flex-1">
              {toast.title && <p className="text-sm font-semibold text-ink">{toast.title}</p>}
              <p className={cn('text-sm leading-relaxed text-ink-muted', !toast.title && 'text-ink')}>{toast.text}</p>
              {toast.action}
            </div>
            <button
              type="button"
              onClick={() => onDismiss(toast.id)}
              aria-label="Tutup pemberitahuan"
              className="-m-1 rounded-lg p-1 text-ink-subtle transition hover:bg-canvas hover:text-ink"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>,
    document.body
  );
}
