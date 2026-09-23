import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../lib/AuthContext'
import { ApiError } from '../lib/http'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { ThemeToggle } from '../components/ui/ThemeToggle'
import { LanguageSwitcher } from '../components/ui/LanguageSwitcher'
import { ArrowRight, Bell, Eye, EyeOff, Search, ShieldCheck, Video } from 'lucide-react'

export function Login() {
  const { login } = useAuth()
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

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
    <div className="login-page">
      <header className="login-header">
        <div className="flex items-center gap-2.5 text-sm font-semibold">
          <span className="brand-symbol"><ShieldCheck size={22} aria-hidden="true" /></span>
          {t('login.title')}
        </div>
        <div className="flex items-center gap-2">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      </header>
      <main className="login-layout">
        <section className="login-story" aria-labelledby="login-platform">
          <div className="login-emblem"><ShieldCheck size={48} strokeWidth={1.3} aria-hidden="true" /></div>
          <h1 id="login-platform">{t('workspace.loginHeadline')}</h1>
          <p>{t('workspace.loginDescription')}</p>
          <ul className="login-capabilities">
            {[
              { icon: Video, label: 'nav.liveWall', detail: 'workspace.loginMonitor' },
              { icon: Search, label: 'nav.findVehicle', detail: 'workspace.loginInvestigate' },
              { icon: Bell, label: 'nav.alerts', detail: 'workspace.loginReview' },
            ].map(({ icon: Icon, label, detail }) => (
              <li key={label}>
                <Icon size={20} aria-hidden="true" />
                <div><strong>{t(label)}</strong><span>{t(detail)}</span></div>
              </li>
            ))}
          </ul>
          <div className="login-story-footer">{t('workspace.console')}<span>Sentinel</span></div>
        </section>
        <section className="login-form-panel">
        <form onSubmit={handleSubmit} aria-labelledby="login-heading" aria-busy={busy}>
          <div className="mb-8">
            <h2 id="login-heading" className="text-2xl font-semibold tracking-tight">{t('command:signInTitle')}</h2>
            <p className="mt-2 text-sm leading-relaxed text-text-secondary">{t('command:signInDescription')}</p>
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
              <div className="relative">
              <Input
                id="login-password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                required
                aria-describedby={error ? 'login-error' : undefined}
                aria-invalid={!!error}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pr-12"
              />
              <button type="button" className="absolute inset-y-0 right-1 flex w-11 items-center justify-center rounded-md text-text-secondary hover:text-accent" aria-label={t(showPassword ? 'command:hidePassword' : 'command:showPassword')} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
              </div>
            </div>
          </div>
          {error && <p id="login-error" role="alert" className="mt-5 rounded-md bg-sev-critical/10 p-3 text-sm text-sev-critical">{error}</p>}
          <Button type="submit" disabled={busy} className="mt-7 min-h-11 w-full justify-between">
            {busy ? t('login.signingIn') : t('login.signIn')}
            <ArrowRight size={18} aria-hidden="true" />
          </Button>
          <p className="login-help"><ShieldCheck size={16} aria-hidden="true" />{t('workspace.authorisedAccess')}</p>
        </form>
        </section>
      </main>
    </div>
  )
}
