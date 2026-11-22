import { Check, Palette } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { cx } from '../../lib/cx'
import { useTheme } from '../../lib/theme'

export function ThemeMenu() {
  const { theme, setTheme, themes } = useTheme()
  const [open, setOpen] = useState(false)
  const container = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => {
      if (container.current && !container.current.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="relative" ref={container}>
      <button
        onClick={() => setOpen((current) => !current)}
        aria-label="Change theme"
        aria-expanded={open}
        title="Theme"
        className="flex items-center gap-1.5 rounded-[7px] border border-[var(--color-line)] px-2.5 py-1.5 text-[11px] text-muted transition-colors hover:border-[var(--color-line-strong)] hover:text-fg"
      >
        <Palette className="size-3.5" />
        <span className="hidden md:inline">{themes.find((entry) => entry.id === theme)?.name}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-[268px] rounded-[12px] border border-[var(--color-line)] bg-[var(--color-surface)] p-1.5 shadow-[0_24px_60px_-24px_rgba(0,0,0,0.7)]">
          <div className="px-2 pb-1.5 pt-1 text-[9.5px] uppercase tracking-[0.14em] text-faint">
            Interface theme
          </div>
          {themes.map((entry) => (
            <button
              key={entry.id}
              onClick={() => { setTheme(entry.id); setOpen(false) }}
              className={cx(
                'flex w-full items-start gap-2.5 rounded-[8px] px-2 py-1.5 text-left transition-colors',
                entry.id === theme ? 'bg-[var(--accent-soft)]' : 'hover:bg-[var(--overlay-2)]',
              )}
            >
              <span className="mt-0.5 flex shrink-0 items-center">
                {entry.swatch.map((color) => (
                  <span
                    key={color}
                    className="-ml-1 size-3.5 rounded-full border border-[var(--color-line)] first:ml-0"
                    style={{ background: color }}
                  />
                ))}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[11.5px] text-fg">{entry.name}</span>
                <span className="block text-[10px] leading-snug text-faint">{entry.description}</span>
              </span>
              {entry.id === theme && <Check className="mt-0.5 size-3.5 shrink-0 text-[var(--color-accent)]" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
