import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { camerasApi } from './api'
import { districtFor } from './districts'
import type { Camera } from './types'
import { usePolling } from './usePolling'

const STORAGE_KEY = 'sentinel-jurisdiction'
export const ALL_JURISDICTIONS = 'all'

interface JurisdictionValue {
  /** A district name, or ALL_JURISDICTIONS for the whole state. */
  scope: string
  setScope: (scope: string) => void
  /** Districts that currently have at least one registered camera. */
  districts: { name: string; cameras: number }[]
  cameras: Camera[] | null
  camerasError: unknown
  refreshCameras: () => void
  districtOf: (cameraId: string) => string | null
  /** Unknown cameras (not in the registry) count as in scope, never hidden. */
  inScope: (cameraId: string) => boolean
}

const JurisdictionContext = createContext<JurisdictionValue | null>(null)

/** The control room's area of responsibility. Every board filters by it, so
 * a district room sees its own cameras and vehicles at state scale. */
export function JurisdictionProvider({ children }: { children: ReactNode }) {
  const [scope, setScopeState] = useState(() => localStorage.getItem(STORAGE_KEY) ?? ALL_JURISDICTIONS)
  const { data: cameras, error: camerasError, refetch: refreshCameras } = usePolling(() => camerasApi.list(), 30000)

  const districtByCamera = useMemo(() => {
    const map = new Map<string, string | null>()
    for (const camera of cameras ?? []) map.set(camera.camera_id, districtFor(camera))
    return map
  }, [cameras])

  const districts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const district of districtByCamera.values()) if (district) counts.set(district, (counts.get(district) ?? 0) + 1)
    return [...counts.entries()].map(([name, count]) => ({ name, cameras: count })).sort((a, b) => a.name.localeCompare(b.name))
  }, [districtByCamera])

  const setScope = useCallback((next: string) => {
    setScopeState(next)
    localStorage.setItem(STORAGE_KEY, next)
  }, [])

  const districtOf = useCallback((cameraId: string) => districtByCamera.get(cameraId) ?? null, [districtByCamera])
  const inScope = useCallback(
    (cameraId: string) => scope === ALL_JURISDICTIONS || !districtByCamera.has(cameraId) || districtByCamera.get(cameraId) === scope,
    [scope, districtByCamera],
  )

  const value = useMemo(
    () => ({ scope, setScope, districts, cameras, camerasError, refreshCameras, districtOf, inScope }),
    [scope, setScope, districts, cameras, camerasError, refreshCameras, districtOf, inScope],
  )
  return <JurisdictionContext.Provider value={value}>{children}</JurisdictionContext.Provider>
}

export function useJurisdiction(): JurisdictionValue {
  const value = useContext(JurisdictionContext)
  if (!value) throw new Error('useJurisdiction must be used inside JurisdictionProvider')
  return value
}
