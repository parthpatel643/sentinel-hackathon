import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { authApi } from './api'
import { getToken, onTokenChange, setToken } from './authStore'
import { ApiError } from './http'
import type { AuthUser } from './types'

interface AuthContextValue {
  user: AuthUser | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  async function refreshUser() {
    if (!getToken()) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      setUser(await authApi.me())
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setUser(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshUser()
    // Fires whenever http.ts clears the token on a 401 from any request,
    // not just this provider's own login/logout — a session that expires
    // mid-use falls back to the login screen on its own.
    return onTokenChange(() => refreshUser())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function login(email: string, password: string) {
    const { access_token } = await authApi.login(email, password)
    setToken(access_token)
    setUser(await authApi.me())
  }

  function logout() {
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
