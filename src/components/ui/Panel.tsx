import type { ReactNode } from 'react'

import { cx } from '../../lib/cx'

interface PanelProps {
  title?: ReactNode
  subtitle?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
  footer?: ReactNode
}

export function Panel({ title, subtitle, action, children, className, bodyClassName, footer }: PanelProps) {
  return (
    <section className={cx('panel flex min-w-0 flex-col', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-[var(--color-line)] px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="truncate text-[12.5px] font-medium tracking-[0.01em] text-fg">{title}</h2>}
            {subtitle && <p className="mt-0.5 truncate text-[11px] text-muted">{subtitle}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </header>
      )}
      <div className={cx('min-h-0 flex-1', bodyClassName ?? 'p-4')}>{children}</div>
      {footer && (
        <footer className="border-t border-[var(--color-line)] px-4 py-2.5 text-[11px] text-muted">
          {footer}
        </footer>
      )}
    </section>
  )
}
