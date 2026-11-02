import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, CheckCircle2, Info, Loader2, X } from 'lucide-react';
import { cn } from '../lib/utils';

/* ------------------------------------------------------------------ */
/* Button                                                              */
/* ------------------------------------------------------------------ */
const BTN_VARIANTS = {
  primary: 'btn btn-primary',
  secondary: 'btn btn-secondary',
  ghost: 'btn btn-ghost',
  danger: 'btn btn-danger',
  warning: 'btn btn-warning',
  success: 'btn btn-success',
};

const BTN_SIZES = { sm: 'btn-sm', md: '', lg: 'btn-lg', xs: 'btn-xs' };

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon: Icon,
  iconRight: IconRight,
  className,
  children,
  disabled,
  type = 'button',
  ...props
}) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cn(BTN_VARIANTS[variant], BTN_SIZES[size], className)}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden="true" />
      ) : (
        Icon && <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      )}
      {children}
      {IconRight && !loading && <IconRight className="h-4 w-4 shrink-0" aria-hidden="true" />}
    </button>
  );
}

export function IconButton({ label, icon: Icon, className, ...props }) {
  return (
    <button type="button" aria-label={label} title={label} className={cn('btn-icon', className)} {...props}>
      <Icon className="h-4 w-4" aria-hidden="true" />
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Surfaces                                                            */
/* ------------------------------------------------------------------ */
export function Card({ as: Tag = 'div', className, children, ...props }) {
  return (
    <Tag className={cn('card', className)} {...props}>
      {children}
    </Tag>
  );
}

export function CardHeader({ title, description, icon: Icon, actions, className }) {
  return (
    <div className={cn('card-header', className)}>
      <div className="flex min-w-0 items-start gap-3">
        {Icon && (
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
            <Icon className="h-4.5 w-4.5" aria-hidden="true" />
          </span>
        )}
        <div className="min-w-0">
          <h2 className="text-base font-semibold leading-6 text-ink">{title}</h2>
          {description && <p className="mt-0.5 text-sm leading-relaxed text-ink-muted">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function PageHeader({ title, description, actions, children }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-xl font-bold tracking-tight text-ink sm:text-2xl">{title}</h1>
        {description && (
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-ink-muted">{description}</p>
        )}
        {children}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Badges                                                              */
/* ------------------------------------------------------------------ */
const TONES = {
  neutral: 'badge-neutral',
  brand: 'badge-brand',
  success: 'badge-success',
  warning: 'badge-warning',
  danger: 'badge-danger',
};

export function Badge({ tone = 'neutral', className, children, ...props }) {
  return (
    <span className={cn('badge', TONES[tone] || TONES.neutral, className)} {...props}>
      {children}
    </span>
  );
}

export function StatusBadge({ meta, dot = false, className, children }) {
  const tone = meta?.tone || 'neutral';
  const dotColor = {
    neutral: 'bg-ink-subtle',
    brand: 'bg-brand-500',
    success: 'bg-success-500',
    warning: 'bg-warning-500',
    danger: 'bg-danger-500',
  }[tone];
  return (
    <Badge tone={tone} className={className}>
      {dot && <span className={cn('h-1.5 w-1.5 rounded-full', dotColor)} aria-hidden="true" />}
      {children ?? meta?.label}
    </Badge>
  );
}

/* ------------------------------------------------------------------ */
/* Form fields                                                         */
/* ------------------------------------------------------------------ */
export function Field({ label, hint, error, required, htmlFor, children, className }) {
  return (
    <div className={className}>
      {label && (
        <label className="label" htmlFor={htmlFor}>
          {label}
          {required && <span className="ml-0.5 text-danger-500">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <p className="mt-1.5 flex items-start gap-1 text-xs text-danger-600">
          <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : (
        hint && <p className="hint">{hint}</p>
      )}
    </div>
  );
}

export function Input({ className, invalid, ...props }) {
  return <input className={cn('input', invalid && 'input-invalid', className)} {...props} />;
}

export function Textarea({ className, invalid, ...props }) {
  return <textarea className={cn('input', invalid && 'input-invalid', className)} {...props} />;
}

export function Select({ className, children, ...props }) {
  return (
    <select className={cn('input cursor-pointer pr-8', className)} {...props}>
      {children}
    </select>
  );
}

export function Checkbox({ label, description, className, id, ...props }) {
  const generated = useId();
  const inputId = id || generated;
  return (
    <div className={cn('flex items-start gap-2.5', className)}>
      <input
        id={inputId}
        type="checkbox"
        className="mt-0.5 h-4 w-4 cursor-pointer rounded border-line text-brand-500 accent-brand-500 focus:ring-brand-400/40"
        {...props}
      />
      {(label || description) && (
        <label htmlFor={inputId} className="cursor-pointer select-none text-sm leading-5 text-ink">
          {label}
          {description && <span className="mt-0.5 block text-xs leading-relaxed text-ink-muted">{description}</span>}
        </label>
      )}
    </div>
  );
}

export function Switch({ checked, onChange, label, description, disabled, id }) {
  const generated = useId();
  const inputId = id || generated;
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <label htmlFor={inputId} className="cursor-pointer text-sm font-medium text-ink">
          {label}
        </label>
        {description && <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{description}</p>}
      </div>
      <button
        id={inputId}
        type="button"
        role="switch"
        aria-checked={!!checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange?.(!checked)}
        className={cn(
          'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50',
          checked ? 'bg-brand-500' : 'bg-[#cfdce8]'
        )}
      >
        <span
          className={cn(
            'inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform',
            checked ? 'translate-x-5' : 'translate-x-0.5'
          )}
        />
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Feedback                                                            */
/* ------------------------------------------------------------------ */
const ALERT_TONES = {
  info: { wrap: 'border-brand-200 bg-brand-50 text-brand-900', icon: Info, iconColor: 'text-brand-600' },
  success: { wrap: 'border-success-100 bg-success-50 text-success-700', icon: CheckCircle2, iconColor: 'text-success-600' },
  warning: { wrap: 'border-warning-100 bg-warning-50 text-warning-700', icon: AlertCircle, iconColor: 'text-warning-600' },
  error: { wrap: 'border-danger-100 bg-danger-50 text-danger-700', icon: AlertCircle, iconColor: 'text-danger-600' },
};

export function Alert({ tone = 'info', title, children, onDismiss, className, action }) {
  const config = ALERT_TONES[tone] || ALERT_TONES.info;
  const Icon = config.icon;
  return (
    <div className={cn('flex items-start gap-3 rounded-xl border p-3.5 text-sm', config.wrap, className)} role="status">
      <Icon className={cn('mt-0.5 h-4.5 w-4.5 shrink-0', config.iconColor)} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold leading-5">{title}</p>}
        {children && <div className={cn('text-sm leading-relaxed', title && 'mt-0.5 opacity-90')}>{children}</div>}
      </div>
      {action}
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Tutup pemberitahuan"
          className="-m-1 rounded-lg p-1 opacity-70 transition hover:opacity-100"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

export function Spinner({ className, label = 'Memuat…' }) {
  return (
    <span className={cn('inline-flex items-center gap-2 text-sm text-ink-muted', className)} role="status">
      <Loader2 className="h-4 w-4 animate-spin text-brand-500" aria-hidden="true" />
      {label}
    </span>
  );
}

export function Skeleton({ className }) {
  return <div className={cn('skeleton h-4 w-full', className)} aria-hidden="true" />;
}

export function LoadingCards({ count = 3 }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-busy="true" aria-label="Memuat data">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card p-5">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-3 h-7 w-20" />
          <Skeleton className="mt-3 h-3 w-32" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, description, action, className }) {
  return (
    <div className={cn('flex flex-col items-center justify-center rounded-2xl border border-dashed border-line bg-canvas/60 px-6 py-12 text-center', className)}>
      {Icon && (
        <span className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-soft text-ink-subtle">
          <Icon className="h-6 w-6" aria-hidden="true" />
        </span>
      )}
      <p className="text-sm font-semibold text-ink">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm leading-relaxed text-ink-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ProgressBar({ value = 0, tone = 'brand', className, label }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  const fill = {
    brand: 'bg-brand-400',
    success: 'bg-success-500',
    warning: 'bg-warning-500',
    danger: 'bg-danger-500',
  }[tone] || 'bg-brand-400';
  return (
    <div className={className}>
      {label && <div className="mb-1.5 flex justify-between text-xs text-ink-muted"><span>{label}</span><span>{Math.round(pct)}%</span></div>}
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-soft"
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={cn('h-full rounded-full transition-all duration-500', fill)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Stat card                                                           */
/* ------------------------------------------------------------------ */
export function StatCard({ label, value, helper, icon: Icon, tone = 'brand', action, className }) {
  const iconTone = {
    brand: 'bg-brand-50 text-brand-600',
    success: 'bg-success-50 text-success-600',
    warning: 'bg-warning-50 text-warning-600',
    danger: 'bg-danger-50 text-danger-600',
    neutral: 'bg-soft text-ink-muted',
  }[tone];
  return (
    <div className={cn('card card-hover flex flex-col p-5', className)}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-ink-muted">{label}</p>
        {Icon && (
          <span className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-xl', iconTone)}>
            <Icon className="h-4.5 w-4.5" aria-hidden="true" />
          </span>
        )}
      </div>
      <p className="mt-2 text-2xl font-bold tracking-tight text-ink">{value}</p>
      {helper && <p className="mt-1 text-xs leading-relaxed text-ink-muted">{helper}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Tabs / segmented                                                    */
/* ------------------------------------------------------------------ */
export function Pills({ items, value, onChange, className, ariaLabel = 'Filter' }) {
  return (
    <div className={cn('no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1 py-1', className)} role="tablist" aria-label={ariaLabel}>
      {items.map((item) => {
        const active = value === item.key;
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.key)}
            className={cn(
              'inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3.5 py-2 text-xs font-semibold transition-colors',
              active
                ? 'border-brand-400 bg-brand-50 text-brand-700'
                : 'border-line bg-surface text-ink-muted hover:bg-soft hover:text-ink'
            )}
          >
            {item.label}
            {item.count !== undefined && item.count !== null && (
              <span
                className={cn(
                  'rounded-full px-1.5 py-0.5 text-[11px] font-bold leading-none',
                  item.highlight ? 'bg-warning-500 text-white' : active ? 'bg-brand-200 text-brand-800' : 'bg-soft text-ink-muted'
                )}
              >
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Segmented({ options, value, onChange, className, ariaLabel = 'Pilihan' }) {
  return (
    <div className={cn('inline-flex rounded-xl border border-line bg-canvas p-1', className)} role="group" aria-label={ariaLabel}>
      {options.map((option) => {
        const active = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors',
              active ? 'bg-surface text-ink shadow-card' : 'text-ink-muted hover:text-ink'
            )}
          >
            {option.icon && <option.icon className="h-3.5 w-3.5" aria-hidden="true" />}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Modal                                                               */
/* ------------------------------------------------------------------ */
export function Modal({ open, onClose, title, description, children, footer, size = 'md', icon: Icon }) {
  const panelRef = useRef(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const timer = window.setTimeout(() => {
      const focusable = panelRef.current?.querySelector(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      focusable?.focus?.();
    }, 30);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      window.clearTimeout(timer);
    };
  }, [open, onClose]);

  if (!open) return null;

  const width = {
    sm: 'sm:max-w-sm',
    md: 'sm:max-w-lg',
    lg: 'sm:max-w-2xl',
  }[size];

  return createPortal(
    <div className="fixed inset-0 z-[80] flex items-end justify-center sm:items-center">
      <div
        className="absolute inset-0 bg-[#101828]/45 backdrop-blur-[2px] animate-fade-in"
        onClick={() => onClose?.()}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          'relative z-10 max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-surface p-5 shadow-popover animate-slide-up sm:rounded-2xl sm:p-6',
          width
        )}
      >
        <div className="flex items-start gap-3">
          {Icon && (
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
              <Icon className="h-5 w-5" aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-lg font-semibold leading-6 text-ink">{title}</h2>
            {description && <p className="mt-1 text-sm leading-relaxed text-ink-muted">{description}</p>}
          </div>
          <button
            type="button"
            onClick={() => onClose?.()}
            aria-label="Tutup dialog"
            className="-mr-1 -mt-1 rounded-lg p-1.5 text-ink-muted transition hover:bg-soft hover:text-ink"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        {children && <div className="mt-4">{children}</div>}

        {footer && <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">{footer}</div>}
      </div>
    </div>,
    document.body
  );
}
