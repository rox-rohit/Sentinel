import type { ReactNode } from 'react'

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: string
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.16em] text-[var(--color-accent)]">
            {eyebrow}
          </div>
        )}
        <h1 className="text-[19px] font-medium tracking-[-0.015em] text-fg">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-[12px] leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

/**
 * A quiet aside. It deliberately carries no amber/alert styling: operational
 * notices belong in the status chips, and long caveat callouts read as noise.
 * The `tone` prop is accepted for existing call sites and no longer changes the
 * rendering.
 */
export function Note({ children }: { children: ReactNode; tone?: 'default' | 'warn' }) {
  return (
    <p className="rounded-[8px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-3 py-2 text-[11px] leading-relaxed text-muted">
      {children}
    </p>
  )
}
