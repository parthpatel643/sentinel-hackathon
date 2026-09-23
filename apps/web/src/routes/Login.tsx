import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../lib/AuthContext'
import { ApiError } from '../lib/http'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { ThemeToggle } from '../components/ui/ThemeToggle'
import { LanguageSwitcher } from '../components/ui/LanguageSwitcher'
import { ArrowRight, Bell, Search, ShieldCheck, Video } from 'lucide-react'

export function Login() {
  const { login } = useAuth()
  const { t } = useTranslation()
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
      setError(err instanceof ApiError ? t('login.errorIncorrect') : t('login.errorUnreachable'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-bg-base text-text-primary">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle px-5 py-4 sm:px-8">
        <div className="flex items-center gap-2.5 text-sm font-semibold">
          <ShieldCheck size={22} className="text-accent" aria-hidden="true" />
          {t('login.title')}
        </div>
        <div className="flex items-center gap-2">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto grid w-full max-w-5xl flex-1 items-center gap-10 px-5 py-10 sm:px-8 lg:grid-cols-2 lg:gap-20 lg:py-20">
        <section className="hidden border-r border-border-subtle py-10 pr-16 lg:block" aria-labelledby="login-platform">
          <ShieldCheck size={42} className="mb-8 text-accent" strokeWidth={1.5} aria-hidden="true" />
          <h1 id="login-platform" className="text-4xl font-semibold leading-tight tracking-tight">{t('login.title')}</h1>
          <p className="mt-4 text-base leading-relaxed text-text-secondary">{t('login.subtitle')}</p>
          <ul className="mt-12 space-y-5 text-sm text-text-secondary">
            {[
              { icon: Video, label: 'nav.liveWall' },
              { icon: Search, label: 'nav.findVehicle' },
              { icon: Bell, label: 'nav.alerts' },
            ].map(({ icon: Icon, label }) => (
              <li key={label} className="flex items-center gap-3">
                <Icon size={18} className="text-accent" aria-hidden="true" />
                {t(label)}
              </li>
            ))}
          </ul>
        </section>
        <form onSubmit={handleSubmit} aria-labelledby="login-heading" aria-busy={busy} className="mx-auto w-full max-w-sm">
          <div className="mb-8">
            <h2 id="login-heading" className="text-2xl font-semibold tracking-tight">{t('login.signIn')}</h2>
            <p className="mt-2 text-sm leading-relaxed text-text-secondary">{t('login.subtitle')}</p>
          </div>
          <div className="space-y-5">
            <div>
              <label htmlFor="login-email" className="mb-2 block text-sm font-medium">{t('login.emailPlaceholder')}</label>
              <Input
                id="login-email"
                name="email"
                type="email"
                autoComplete="username"
                required
                autoFocus
                aria-describedby={error ? 'login-error' : undefined}
                aria-invalid={!!error}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full"
              />
            </div>
            <div>
              <label htmlFor="login-password" className="mb-2 block text-sm font-medium">{t('login.passwordPlaceholder')}</label>
              <Input
                id="login-password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                aria-describedby={error ? 'login-error' : undefined}
                aria-invalid={!!error}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full"
              />
            </div>
          </div>
          {error && <p id="login-error" role="alert" className="mt-5 rounded-md bg-sev-critical/10 p-3 text-sm text-sev-critical">{error}</p>}
          <Button type="submit" disabled={busy} className="mt-7 min-h-11 w-full justify-between">
            {busy ? t('login.signingIn') : t('login.signIn')}
            <ArrowRight size={18} aria-hidden="true" />
          </Button>
        </form>
      </main>
    </div>
  )
}
