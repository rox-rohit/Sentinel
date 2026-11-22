import { cx } from '../../lib/cx'

export function HealthMeter({ value, className }: { value: number; className?: string }) {
  const color =
    value >= 80 ? 'var(--color-good)'
      : value >= 60 ? 'var(--color-accent)'
        : value >= 40 ? 'var(--color-warn)'
          : 'var(--color-critical)'
  return (
    <div className={cx('h-1.5 w-full overflow-hidden rounded-full bg-[var(--track)]', className)}>
      <div
        className="h-full rounded-full transition-[width] duration-500"
        style={{ width: `${Math.max(2, Math.min(100, value))}%`, background: color }}
      />
    </div>
  )
}

export function RiskMeter({ value, className }: { value: number; className?: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div className={cx('flex items-center gap-2', className)}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--track)]">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.max(2, pct)}%`,
            background: pct >= 70 ? 'var(--color-critical)' : pct >= 40 ? 'var(--color-warn)' : 'var(--color-accent)',
          }}
        />
      </div>
      <span className="numeric w-9 text-right text-[11px] text-muted">{pct.toFixed(0)}%</span>
    </div>
  )
}

export function Ring({ value, label, size = 96 }: { value: number; label?: string; size?: number }) {
  const stroke = 7
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const color =
    value >= 80 ? 'var(--color-good)'
      : value >= 60 ? 'var(--color-accent)'
        : value >= 40 ? 'var(--color-warn)'
          : 'var(--color-critical)'
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none"
          stroke="var(--track-strong)" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={color} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - Math.max(0, Math.min(100, value)) / 100)}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="numeric text-[20px] font-medium leading-none">{value.toFixed(0)}</span>
        {label && <span className="mt-1 text-[9px] uppercase tracking-[0.12em] text-faint">{label}</span>}
      </div>
    </div>
  )
}
