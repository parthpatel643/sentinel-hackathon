/** Thin fetch wrapper for core_api. One place to change the base URL, error
 * shape and JSON handling — every route module calls through this, never
 * `fetch` directly. */

import { getToken, setToken } from './authStore'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:18000'

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `API error ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/api/v1/auth/login')) {
      // The token is missing/expired/invalid — clear it so the app falls
      // back to the login screen instead of looping on 401s.
      setToken(null)
    }
    let detail: unknown = null
    try {
      detail = await response.json()
    } catch {
      detail = await response.text()
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function get<T>(path: string): Promise<T> {
  return request<T>(path)
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined })
}

function patch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
}

/** For binary downloads (e.g. the Movement Report zip) — everything else
 * in this file assumes a JSON body, which a zip response is not. */
async function getBlob(path: string): Promise<{ blob: Blob; filename: string }> {
  const token = getToken()
  const response = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    if (response.status === 401) setToken(null)
    let detail: unknown = null
    try {
      detail = await response.json()
    } catch {
      detail = await response.text()
    }
    throw new ApiError(response.status, detail)
  }
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^"]+)"?/.exec(disposition)
  const filename = match?.[1] ?? 'download'
  return { blob: await response.blob(), filename }
}

/** For multipart file uploads (bulk CSV import) — must NOT set a JSON
 * Content-Type header, or the browser's auto-generated multipart boundary
 * (which request() would otherwise override) never reaches the server. */
async function postForm<T>(path: string, formData: FormData): Promise<T> {
  const token = getToken()
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    body: formData,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    if (response.status === 401) setToken(null)
    let detail: unknown = null
    try {
      detail = await response.json()
    } catch {
      detail = await response.text()
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

export { get, patch, post, getBlob, postForm }
export { API_BASE }
