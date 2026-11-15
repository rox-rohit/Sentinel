import { useCallback, useEffect, useState } from 'react'

import { loadDataset, type DatasetState } from './api'

export interface SentinelDataState {
  loading: boolean
  dataset: DatasetState | null
  refresh: () => void
}

export function useSentinelData(): SentinelDataState {
  const [dataset, setDataset] = useState<DatasetState | null>(null)
  const [loading, setLoading] = useState(true)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    loadDataset().then((next) => {
      if (cancelled) return
      setDataset(next)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [nonce])

  const refresh = useCallback(() => setNonce((value) => value + 1), [])
  return { loading, dataset, refresh }
}
