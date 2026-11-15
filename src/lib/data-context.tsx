import { createContext, useContext } from 'react'

import type { DatasetState } from './api'

const DataContext = createContext<DatasetState | null>(null)

export const DataProvider = DataContext.Provider

export function useData(): DatasetState {
  const value = useContext(DataContext)
  if (!value) throw new Error('useData must be used inside DataProvider')
  return value
}
