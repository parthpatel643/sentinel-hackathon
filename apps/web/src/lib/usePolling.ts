import { useEffect, useRef, useState } from 'react'

interface PollResult<T> {
  data: T | null
  error: unknown
  loading: boolean
  refetch: () => void
}

/** Fetch once, then re-fetch every `intervalMs` — the console is a live
 * situational-awareness screen, not a request-once report, so every list
 * screen is built on this rather than one-shot `useEffect(fetch, [])`.
 *
 * Skips the state update (and the re-render it would cause) when a poll
 * returns byte-for-byte the same payload as last time — a stable watchlist
 * of five alerts must not re-render, re-flow and repaint every six seconds
 * just because a heartbeat asked the API again (docs/03-UX-DESIGN.md's
 * "calm under pressure" principle applies to the DOM, not just colour). */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 5000, deps: unknown[] = []): PollResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher
  const lastPayloadRef = useRef<string | null>(null)
  const hasDataRef = useRef(false)

  useEffect(() => {
    let cancelled = false
    if (!hasDataRef.current) setLoading(true)
    fetcherRef
      .current()
      .then((result) => {
        if (cancelled) return
        const serialised = JSON.stringify(result)
        if (serialised !== lastPayloadRef.current) {
          lastPayloadRef.current = serialised
          setData(result)
        }
        hasDataRef.current = true
        setError(null)
      })
      .catch((err) => {
        if (!cancelled) setError(err)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    if (intervalMs <= 0) return () => { cancelled = true }
    const id = setInterval(() => setTick((t) => t + 1), intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, tick, ...deps])

  return { data, error, loading, refetch: () => setTick((t) => t + 1) }
}
