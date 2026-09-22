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

export { get, patch, post }
export { API_BASE }
