import type { ReactNode } from 'react'

import type { HealthCategory, Severity } from '../../data/types'
import { cx } from '../../lib/cx'

const SEVERITY_STYLES: Record<string, string> = {
  healthy: 'bg-[var(--good-soft)] text-[var(--color-good)] ring-[var(--good-line)]',
  normal: 'bg-[var(--good-soft)] text-[var(--color-good)] ring-[var(--good-line)]',
  attention: 'bg-[var(--accent-2-soft)] text-[var(--color-accent-3)] ring-[var(--accent-2-line)]',
  low: 'bg-[var(--accent-2-soft)] text-[var(--color-accent-3)] ring-[var(--accent-2-line)]',
  medium: 'bg-[var(--warn-soft)] text-[var(--color-warn)] ring-[var(--warn-line)]',
  warning: 'bg-[var(--warn-soft)] text-[var(--color-warn)] ring-[var(--warn-line)]',
  high: 'bg-[var(--bad-soft)] text-[var(--color-bad)] ring-[var(--bad-line)]',
  critical: 'bg-[var(--critical-soft)] text-[var(--color-critical)] ring-[var(--critical-line)]',
  neutral: 'bg-[var(--overlay-2)] text-muted ring-[var(--color-line-strong)]',
}

export function Badge({
  children,
  tone = 'neutral',
  className,
  dot = false,
}: {
  children: ReactNode
  tone?: HealthCategory | Severity | 'neutral'
  className?: string
  dot?: boolean
}) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-[3px] text-[10.5px] font-medium uppercase tracking-[0.06em] ring-1 ring-inset',
        SEVERITY_STYLES[tone] ?? SEVERITY_STYLES.neutral,
        className,
      )}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  )
}

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx('text-[10px] font-medium uppercase tracking-[0.14em] text-faint', className)}>
      {children}
    </span>
  )
}
