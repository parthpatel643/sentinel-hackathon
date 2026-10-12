import { useEffect, useState } from 'react'
import { detectionsApi } from './api'

export type SnapshotState = { status: 'none' } | { status: 'loading' } | { status: 'ready'; url: string } | { status: 'failed' }

/** The evidence frame for a detection. Snapshots are bearer-authed, which a
 * plain <img src> cannot call, so they load as a blob behind an object URL. */
export function useSnapshot(eventId: string | null | undefined, available = true): SnapshotState {
  const [state, setState] = useState<SnapshotState>({ status: 'none' })

  useEffect(() => {
    if (!eventId || !available) {
      setState({ status: 'none' })
      return
    }
    let cancelled = false
    let url: string | null = null
    setState({ status: 'loading' })
    detectionsApi
      .snapshotBlob(eventId)
      .then((result) => {
        if (cancelled) return
        url = URL.createObjectURL(result.blob)
        setState({ status: 'ready', url })
      })
      .catch(() => !cancelled && setState({ status: 'failed' }))
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [eventId, available])

  return state
}
