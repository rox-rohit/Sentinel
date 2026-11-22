import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export type ThemeId = 'sentinel' | 'obsidian' | 'daylight' | 'graphite' | 'aurora'

export interface ThemeMeta {
  id: ThemeId
  name: string
  description: string
  scheme: 'dark' | 'light'
  swatch: [string, string, string]
}

export const THEMES: ThemeMeta[] = [
  {
    id: 'sentinel',
    name: 'Sentinel',
    description: 'Midnight command centre with cyan telemetry.',
    scheme: 'dark',
    swatch: ['#07090c', '#35d6f2', '#2dd4a7'],
  },
  {
    id: 'obsidian',
    name: 'Obsidian',
    description: 'True black, monochrome steel, zero glow.',
    scheme: 'dark',
    swatch: ['#000000', '#e6e8eb', '#e0b878'],
  },
  {
    id: 'daylight',
    name: 'Daylight',
    description: 'Paper white surfaces with ink-blue accents.',
    scheme: 'light',
    swatch: ['#ffffff', '#0b6bcb', '#0b7f5a'],
  },
  {
    id: 'graphite',
    name: 'Graphite',
    description: 'Warm stone neutrals with deep teal.',
    scheme: 'light',
    swatch: ['#f3f2ef', '#0f766e', '#a16207'],
  },
  {
    id: 'aurora',
    name: 'Aurora',
    description: 'Indigo night with violet and cyan gradients.',
    scheme: 'dark',
    swatch: ['#080614', '#a78bfa', '#22d3ee'],
  },
]

const STORAGE_KEY = 'sentinel.theme'
const DEFAULT_THEME: ThemeId = 'sentinel'

function isTheme(value: string | null | undefined): value is ThemeId {
  return THEMES.some((theme) => theme.id === value)
}

function storedTheme(): ThemeId {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (isTheme(saved)) return saved
  } catch {
    // Storage can be blocked; the default theme still works.
  }
  return DEFAULT_THEME
}

function applyTheme(theme: ThemeId): void {
  const meta = THEMES.find((entry) => entry.id === theme) ?? THEMES[0]
  const root = document.documentElement
  root.dataset.theme = meta.id
  root.style.colorScheme = meta.scheme
  const metaTag = document.querySelector('meta[name="theme-color"]')
  if (metaTag) metaTag.setAttribute('content', meta.swatch[0])
}

interface ThemeContextValue {
  theme: ThemeId
  meta: ThemeMeta
  themes: ThemeMeta[]
  setTheme: (theme: ThemeId) => void
  cycleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeId>(storedTheme)

  useEffect(() => {
    applyTheme(theme)
    try {
      window.localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // Ignore storage failures; the in-memory choice still applies.
    }
  }, [theme])

  const setTheme = useCallback((next: ThemeId) => setThemeState(next), [])
  const cycleTheme = useCallback(() => {
    setThemeState((current) => {
      const index = THEMES.findIndex((entry) => entry.id === current)
      return THEMES[(index + 1) % THEMES.length].id
    })
  }, [])

  const value = useMemo<ThemeContextValue>(() => {
    const meta = THEMES.find((entry) => entry.id === theme) ?? THEMES[0]
    return { theme, meta, themes: THEMES, setTheme, cycleTheme }
  }, [theme, setTheme, cycleTheme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used inside ThemeProvider')
  return context
}
