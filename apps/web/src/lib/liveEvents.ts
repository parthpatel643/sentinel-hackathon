/** The console's live channel: `GET /api/v1/events/stream`, read with `fetch`
 * so the bearer token travels in a header rather than a URL. One connection
 * is shared by every listener; it reconnects with backoff, and the server ends
 * each connection after ~30 s by design, which is an immediate reconnect, not
 * an error. Polling stays in place everywhere as the fallback. */

import { useEffect, useRef } from 'react'
import { getToken, setToken } from './authStore'
import { apiUrl } from './http'

export type LiveEventKind = 'alert' | 'zone_event' | 'camera_event'
type Listener = (kind: LiveEventKind, data: unknown) => void

const listeners = new Set<Listener>()
let controller: AbortController | null = null

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const id = setTimeout(resolve, ms)
    signal.addEventListener('abort', () => { clearTimeout(id); resolve() }, { once: true })
  })
}

function dispatch(block: string) {
  let kind = ''
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) kind = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if ((kind !== 'alert' && kind !== 'zone_event' && kind !== 'camera_event') || data.length === 0) return
  let payload: unknown
  try {
    payload = JSON.parse(data.join('\n'))
  } catch {
    return
  }
  for (const listener of listeners) listener(kind, payload)
}

async function run(signal: AbortSignal) {
  let backoff = 1000
  while (!signal.aborted) {
    const token = getToken()
    if (!token) {
      await sleep(2000, signal)
      continue
    }
    try {
      const response = await fetch(apiUrl('/api/v1/events/stream'), {
        headers: { Authorization: `Bearer ${token}` },
        signal,
      })
      if (response.status === 401) {
        setToken(null)
        await sleep(2000, signal)
        continue
      }
      if (!response.ok || !response.body) throw new Error(`stream ${response.status}`)
      backoff = 1000
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
      let buffer = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += value
        let boundary = buffer.indexOf('\n\n')
        while (boundary !== -1) {
          dispatch(buffer.slice(0, boundary))
          buffer = buffer.slice(boundary + 2)
          boundary = buffer.indexOf('\n\n')
        }
      }
      // The server closes each connection on purpose; come straight back.
      continue
    } catch {
      if (signal.aborted) return
    }
    await sleep(backoff, signal)
    backoff = Math.min(backoff * 2, 15000)
  }
}

export function subscribeLiveEvents(listener: Listener): () => void {
  listeners.add(listener)
  if (!controller) {
    controller = new AbortController()
    void run(controller.signal)
  }
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0 && controller) {
      controller.abort()
      controller = null
    }
  }
}

/** Calls `handler` for every live event while the component is mounted. */
export function useLiveEvents(handler: Listener): void {
  const ref = useRef(handler)
  useEffect(() => {
    ref.current = handler
  })
  useEffect(() => subscribeLiveEvents((kind, data) => ref.current(kind, data)), [])
}
