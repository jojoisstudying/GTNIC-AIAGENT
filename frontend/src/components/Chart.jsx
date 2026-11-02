import { useMemo } from 'react';
import { cn } from '../lib/utils';
import { fmtCompact, fmtNumber } from '../lib/format';

/**
 * Bar chart sederhana (SVG) untuk metrik per postingan.
 * Sengaja tanpa library tambahan agar bundle tetap ringan.
 */
export function BarChart({ data, metric = 'reach', height = 200, className, emptyLabel = 'Belum ada data metrik.' }) {
  const points = useMemo(
    () => (data || []).filter((d) => d && d[metric] !== null && d[metric] !== undefined).slice(-12),
    [data, metric]
  );

  if (points.length === 0) {
    return (
      <div
        className={cn('flex items-center justify-center rounded-xl border border-dashed border-line bg-canvas text-sm text-ink-muted', className)}
        style={{ height }}
      >
        {emptyLabel}
      </div>
    );
  }

  const max = Math.max(...points.map((p) => Number(p[metric]) || 0), 1);
  const barGap = 8;
  const width = 640;
  const labelSpace = 34;
  const plotHeight = height - labelSpace;
  const barWidth = Math.max(10, (width - barGap * (points.length - 1)) / points.length);

  return (
    <div className={cn('w-full', className)}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Grafik ${metric} per postingan`}
        preserveAspectRatio="none"
        style={{ height }}
      >
        {[0.25, 0.5, 0.75, 1].map((tick) => (
          <line
            key={tick}
            x1="0"
            x2={width}
            y1={plotHeight - plotHeight * tick}
            y2={plotHeight - plotHeight * tick}
            stroke="#EDF3F9"
            strokeWidth="1"
          />
        ))}
        {points.map((point, index) => {
          const value = Number(point[metric]) || 0;
          const barHeight = Math.max(3, (value / max) * (plotHeight - 14));
          const x = index * (barWidth + barGap);
          const y = plotHeight - barHeight;
          return (
            <g key={point.id ?? `${index}-${point.date ?? ''}`}>
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={barHeight}
                rx="6"
                fill={index === points.length - 1 ? '#36AEE8' : '#8FD8FC'}
              >
                <title>{`${point.topic || 'Postingan'} — ${metric}: ${fmtNumber(value)}`}</title>
              </rect>
              <text
                x={x + barWidth / 2}
                y={plotHeight + 16}
                textAnchor="middle"
                fontSize="10"
                fill="#94A3B8"
              >
                {point.date ? String(point.date).slice(5) : `#${index + 1}`}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex items-center justify-between text-xs text-ink-muted">
        <span>{points.length} postingan terakhir</span>
        <span>
          Tertinggi: <strong className="text-ink">{fmtCompact(max)}</strong>
        </span>
      </div>
    </div>
  );
}

/** Donut ringkas untuk komposisi (mis. status konten). */
export function DonutChart({ segments, size = 148, thickness = 16, centerLabel, centerValue }) {
  const total = segments.reduce((sum, s) => sum + (Number(s.value) || 0), 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center sm:gap-6">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={centerLabel || 'Komposisi'}>
        <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#EDF3F9" strokeWidth={thickness} />
          {total > 0 &&
            segments.map((segment) => {
              const value = Number(segment.value) || 0;
              if (value <= 0) return null;
              const length = (value / total) * circumference;
              const dash = `${Math.max(0, length - 3)} ${circumference}`;
              const element = (
                <circle
                  key={segment.label}
                  cx={size / 2}
                  cy={size / 2}
                  r={radius}
                  fill="none"
                  stroke={segment.color}
                  strokeWidth={thickness}
                  strokeDasharray={dash}
                  strokeDashoffset={-offset}
                  strokeLinecap="round"
                >
                  <title>{`${segment.label}: ${value}`}</title>
                </circle>
              );
              offset += length;
              return element;
            })}
        </g>
        <text x="50%" y="47%" textAnchor="middle" fontSize="22" fontWeight="700" fill="#243447">
          {centerValue ?? total}
        </text>
        <text x="50%" y="62%" textAnchor="middle" fontSize="10" fill="#64748B">
          {centerLabel || 'total'}
        </text>
      </svg>
      <ul className="w-full space-y-2 text-sm">
        {segments.map((segment) => (
          <li key={segment.label} className="flex items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-2 text-ink-muted">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: segment.color }} />
              <span className="truncate">{segment.label}</span>
            </span>
            <span className="shrink-0 font-semibold text-ink">{fmtNumber(segment.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
