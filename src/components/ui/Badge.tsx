import type { ReactNode } from 'react'

import type { HealthCategory, Severity } from '../../data/types'
import { cx } from '../../lib/cx'

const SEVERITY_STYLES: Record<string, string> = {
  healthy: 'bg-[rgb(45_212_167_/_0.12)] text-[var(--color-good)] ring-[rgb(45_212_167_/_0.28)]',
  normal: 'bg-[rgb(45_212_167_/_0.10)] text-[var(--color-good)] ring-[rgb(45_212_167_/_0.24)]',
  attention: 'bg-[rgb(125_211_252_/_0.10)] text-[var(--color-accent-3)] ring-[rgb(125_211_252_/_0.25)]',
  low: 'bg-[rgb(125_211_252_/_0.10)] text-[var(--color-accent-3)] ring-[rgb(125_211_252_/_0.25)]',
  medium: 'bg-[rgb(245_165_36_/_0.12)] text-[var(--color-warn)] ring-[rgb(245_165_36_/_0.28)]',
  warning: 'bg-[rgb(245_165_36_/_0.12)] text-[var(--color-warn)] ring-[rgb(245_165_36_/_0.28)]',
  high: 'bg-[rgb(244_73_93_/_0.12)] text-[var(--color-bad)] ring-[rgb(244_73_93_/_0.30)]',
  critical: 'bg-[rgb(255_77_109_/_0.14)] text-[var(--color-critical)] ring-[rgb(255_77_109_/_0.34)]',
  neutral: 'bg-white/[0.04] text-muted ring-white/10',
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
