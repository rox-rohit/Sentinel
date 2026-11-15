import { useCallback, useEffect, useState } from 'react'

function currentPath(): string {
  return window.location.pathname || '/'
}

export function usePath(): string {
  const [path, setPath] = useState(currentPath)
  useEffect(() => {
    const onChange = () => setPath(currentPath())
    window.addEventListener('popstate', onChange)
    return () => window.removeEventListener('popstate', onChange)
  }, [])
  return path
}

export function navigate(to: string): void {
  if (to === currentPath()) return
  window.history.pushState({}, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
  window.scrollTo({ top: 0, behavior: 'instant' })
}

export function useNavigate() {
  return useCallback((to: string) => navigate(to), [])
}
