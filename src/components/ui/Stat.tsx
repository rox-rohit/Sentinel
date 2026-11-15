import type { ReactNode } from 'react'

import { cx } from '../../lib/cx'
import { Label } from './Badge'

export function Stat({
  label,
  value,
  unit,
  hint,
  icon,
  tone = 'default',
  className,
}: {
  label: string
  value: ReactNode
  unit?: string
  hint?: ReactNode
  icon?: ReactNode
  tone?: 'default' | 'good' | 'warn' | 'bad' | 'accent'
  className?: string
}) {
  const toneClass = {
    default: 'text-fg',
    good: 'text-[var(--color-good)]',
    warn: 'text-[var(--color-warn)]',
    bad: 'text-[var(--color-bad)]',
    accent: 'text-[var(--color-accent)]',
  }[tone]
  return (
    <div className={cx('panel px-4 py-3.5', className)}>
      <div className="flex items-start justify-between gap-2">
        <Label>{label}</Label>
        {icon && <span className="text-faint">{icon}</span>}
      </div>
      <div className="mt-2 flex items-baseline gap-1.5">
        <span className={cx('numeric text-[26px] leading-none font-medium', toneClass)}>{value}</span>
        {unit && <span className="text-[11px] text-muted">{unit}</span>}
      </div>
      {hint && <div className="mt-2 text-[11px] text-muted">{hint}</div>}
    </div>
  )
}

export function MiniStat({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="raised px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.1em] text-faint">{label}</div>
      <div className={cx('numeric mt-1 text-[15px]', tone ?? 'text-fg')}>{value}</div>
    </div>
  )
}
