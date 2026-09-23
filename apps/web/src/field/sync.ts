import { useCallback, useEffect, useState } from 'react'
import { fieldApi } from '../lib/api'
import {
  listQueuedSightings,
  removeQueuedSighting,
  updateQueuedSighting,
  type QueuedSighting,
} from './outbox'

const LAST_SYNCED_KEY = 'sentinel-field-last-synced'

/** Drains the offline outbox whenever the browser reports it's online —
 * on mount, on the `online` event, and on a periodic tick (some devices
 * don't fire `online` reliably after a long offline stretch). Exposes
 * enough state for the Field PWA's top bar to show "queued: N" and
 * "last synced: …", per docs/03-UX-DESIGN.md §5's explicit last-synced
 * requirement — an officer must always know whether they're looking at
 * fresh data. */
export function useOutboxSync() {
  const [pendingCount, setPendingCount] = useState(0)
  const [syncing, setSyncing] = useState(false)
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(
    () => localStorage.getItem(LAST_SYNCED_KEY),
  )

  const refreshPendingCount = useCallback(async () => {
    const queued = await listQueuedSightings()
    setPendingCount(queued.length)
  }, [])

  const drain = useCallback(async () => {
    if (!navigator.onLine) return
    setSyncing(true)
    try {
      const queued = await listQueuedSightings()
      for (const item of queued) {
        try {
          await fieldApi.submitSighting({
            clientReportId: item.clientReportId,
            plateText: item.plateText,
            lat: item.lat,
            lon: item.lon,
            notes: item.notes,
            photo: item.photoBlob,
          })
          await removeQueuedSighting(item.clientReportId)
        } catch (err) {
          // Leave it queued — a bad connection mid-upload must not lose the
          // report, only delay it to the next drain attempt.
          const failed: QueuedSighting = {
            ...item,
            attempts: item.attempts + 1,
            lastError: err instanceof Error ? err.message : 'Upload failed',
          }
          await updateQueuedSighting(failed)
        }
      }
      const now = new Date().toISOString()
      localStorage.setItem(LAST_SYNCED_KEY, now)
      setLastSyncedAt(now)
    } finally {
      await refreshPendingCount()
      setSyncing(false)
    }
  }, [refreshPendingCount])

  useEffect(() => {
    refreshPendingCount()
    drain()
    window.addEventListener('online', drain)
    const interval = setInterval(drain, 30_000)
    return () => {
      window.removeEventListener('online', drain)
      clearInterval(interval)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { pendingCount, syncing, lastSyncedAt, drainNow: drain, refreshPendingCount }
}
