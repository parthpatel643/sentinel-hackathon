import { useState, type FormEvent } from 'react'
import { useAuth } from '../lib/AuthContext'
import { ApiError } from '../lib/http'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { ShieldCheck } from 'lucide-react'

export function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      setError(err instanceof ApiError ? 'Incorrect email or password.' : 'Could not reach the API.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-bg-base">
      <form onSubmit={handleSubmit} className="flex w-full max-w-sm flex-col gap-5 p-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent/15 text-accent">
            <ShieldCheck size={22} strokeWidth={2.25} />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-text-primary">Sentinel Platform</h1>
            <p className="text-sm text-text-tertiary">Sign in to the Operator Console</p>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <Input
            type="email"
            required
            autoFocus
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            type="password"
            required
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && <p className="text-sm text-sev-critical">{error}</p>}

        <Button type="submit" disabled={busy} className="w-full">
          {busy ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </div>
  )
}
