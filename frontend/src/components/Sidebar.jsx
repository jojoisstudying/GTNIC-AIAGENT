import { Sparkles, X } from 'lucide-react';
import { NAV_GROUPS } from '../lib/nav';
import { cn } from '../lib/utils';

function LogoMark({ className }) {
  return (
    <svg viewBox="0 0 40 40" className={className} role="img" aria-label="Logo GTNIC">
      <rect width="40" height="40" rx="12" fill="#58C4F5" />
      <path
        d="M27.5 14.2a9 9 0 1 0 1.9 8.1h-8.2v-3.6h12.1v1.8A12.6 12.6 0 1 1 28.8 10l-3 2.8a8.98 8.98 0 0 0 1.7 1.4Z"
        fill="#08303F"
      />
    </svg>
  );
}

export default function Sidebar({ activeTab, onNavigate, badges = {}, brandName, onClose, online = true }) {
  return (
    <div className="flex h-full flex-col bg-surface">
      {/* Brand */}
      <div className="flex items-center gap-3 border-b border-line px-5 py-4">
        <LogoMark className="h-10 w-10 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-bold tracking-tight text-ink">GTNIC</p>
          <p className="truncate text-xs text-ink-muted">Asisten Pemasaran AI</p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Tutup menu"
            className="rounded-lg p-1.5 text-ink-muted transition hover:bg-soft hover:text-ink lg:hidden"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Navigasi utama">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-5 last:mb-0">
            <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-subtle">
              {group.label}
            </p>
            <ul className="space-y-1">
              {group.items.map((item) => {
                const active = activeTab === item.key;
                const count = item.badge ? badges[item.badge] || 0 : 0;
                const Icon = item.icon;
                return (
                  <li key={item.key}>
                    <button
                      type="button"
                      onClick={() => onNavigate(item.key)}
                      aria-current={active ? 'page' : undefined}
                      className={cn(
                        'group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition-colors',
                        active
                          ? 'bg-brand-50 text-brand-800'
                          : 'text-ink-muted hover:bg-canvas hover:text-ink'
                      )}
                    >
                      <Icon
                        className={cn('h-4.5 w-4.5 shrink-0', active ? 'text-brand-600' : 'text-ink-subtle group-hover:text-ink-muted')}
                        aria-hidden="true"
                      />
                      <span className="min-w-0 flex-1 truncate">{item.label}</span>
                      {count > 0 && (
                        <span
                          className={cn(
                            'shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-bold leading-none',
                            active ? 'bg-brand-400 text-[#08303f]' : 'bg-warning-50 text-warning-700'
                          )}
                        >
                          {count > 99 ? '99+' : count}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-line p-3">
        <div className="rounded-xl bg-canvas p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-ink">
            <span
              className={cn('h-2 w-2 rounded-full', online ? 'bg-success-500' : 'bg-danger-500')}
              aria-hidden="true"
            />
            {online ? 'Layanan AI terhubung' : 'Layanan AI tidak terdeteksi'}
          </div>
          <p className="mt-1 truncate text-[11px] text-ink-muted">
            {brandName ? `Brand: ${brandName}` : 'Brand belum diatur'}
          </p>
          <button
            type="button"
            onClick={() => onNavigate('generator')}
            className="mt-2.5 inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-brand-400 px-3 py-2 text-xs font-semibold text-[#08303f] transition hover:bg-brand-500"
          >
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Buat konten baru
          </button>
        </div>
      </div>
    </div>
  );
}
