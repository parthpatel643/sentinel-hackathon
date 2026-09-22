/** A plain localStorage-backed token store — not a React hook, so
 * `lib/http.ts` (which has no React dependency) can read the current token
 * on every request without a context/provider threaded through it.
 * `AuthProvider` is the thin React layer on top that makes login state
 * re-render the app. */

const STORAGE_KEY = 'sentinel.auth.token'

let currentToken: string | null = localStorage.getItem(STORAGE_KEY)
const listeners = new Set<(token: string | null) => void>()

export function getToken(): string | null {
  return currentToken
}

export function setToken(token: string | null): void {
  currentToken = token
  if (token) localStorage.setItem(STORAGE_KEY, token)
  else localStorage.removeItem(STORAGE_KEY)
  for (const listener of listeners) listener(token)
}

export function onTokenChange(listener: (token: string | null) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
