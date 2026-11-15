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

export function Note({ children, tone = 'default' }: { children: ReactNode; tone?: 'default' | 'warn' }) {
  return (
    <p
      className={
        tone === 'warn'
          ? 'rounded-[8px] border border-[rgb(245_165_36_/_0.22)] bg-[rgb(245_165_36_/_0.06)] px-3 py-2 text-[11px] leading-relaxed text-[#e8c58a]'
          : 'rounded-[8px] border border-[var(--color-line)] bg-white/[0.02] px-3 py-2 text-[11px] leading-relaxed text-muted'
      }
    >
      {children}
    </p>
  )
}
