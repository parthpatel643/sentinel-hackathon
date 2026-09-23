import { useState } from 'react'
import { ArrowLeft, CheckCircle2, Search, ShieldAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { fieldApi } from '../lib/api'
import { ApiError } from '../lib/http'
import type { PlateLookup } from '../lib/types'

/** docs/03-UX-DESIGN.md §5.2: "result shows the vehicle's status (clear /
 * stolen / wanted) as a full-screen colour-and-icon verdict readable at
 * arm's length in sunlight." A big plate input (native mobile keyboards
 * already handle alphanumeric entry well one-handed — a fully custom
 * on-screen keypad wasn't worth the extra complexity here) rather than a
 * literal numeric-only keypad, since Indian plates mix letters and digits. */
export function FieldLookup() {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [result, setResult] = useState<PlateLookup | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function resetDraft() {
    setInput('')
    setError(null)
  }

  async function search() {
    if (!input.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      setResult(await fieldApi.lookup(input.trim()))
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : t('field.lookup.unreachable'))
    } finally {
      setLoading(false)
    }
  }

  if (result) {
    const isClear = result.status === 'clear'
    return (
      <section className="flex min-h-full flex-col p-5 sm:p-8" aria-labelledby="lookup-result-heading">
        <h1 id="lookup-result-heading" className="text-xl font-semibold">{t('field.nav.lookup')}</h1>
        <div role="status" className="my-auto py-8">
          <div className={`flex flex-col items-center gap-4 rounded-lg p-6 text-center ${isClear ? 'bg-ok/10' : 'bg-sev-critical/10'}`}>
            {isClear ? (
              <CheckCircle2 size={56} className="text-ok" aria-hidden="true" />
            ) : (
              <ShieldAlert size={56} className="text-sev-critical" aria-hidden="true" />
            )}
            <p className={`text-2xl font-semibold ${isClear ? 'text-ok' : 'text-sev-critical'}`}>
              {t(`field.lookup.status.${result.status}`, { defaultValue: result.status })}
            </p>
            <p className="plate-mono break-all text-3xl font-bold text-text-primary">{result.plate_normalised}</p>
          </div>
          <p className="mt-5 text-center text-sm leading-relaxed text-text-secondary">
            {result.last_seen_at
              ? result.last_seen_camera_name
                ? t('field.lookup.lastSeenAt', {
                    date: new Date(result.last_seen_at).toLocaleString(),
                    camera: result.last_seen_camera_name,
                  })
                : t('field.lookup.lastSeen', { date: new Date(result.last_seen_at).toLocaleString() })
              : t('field.lookup.noSightings')}
          </p>
        </div>
        <button
          onClick={() => {
            setResult(null)
            setInput('')
          }}
          className="flex min-h-12 items-center justify-center gap-2 rounded-md border border-border-strong bg-bg-raised px-4 py-3 text-sm font-medium hover:bg-bg-hover focus-visible:outline-2 focus-visible:outline-accent"
        >
          <ArrowLeft size={18} aria-hidden="true" />
          {t('field.lookup.lookupAnother')}
        </button>
      </section>
    )
  }

  return (
    <section className="p-5 sm:p-8" aria-labelledby="lookup-heading">
      <h1 id="lookup-heading" className="text-2xl font-semibold tracking-tight">{t('field.nav.lookup')}</h1>
      <p className="mt-2 text-sm leading-relaxed text-text-secondary">{t('field.lookup.prompt')}</p>
      <form onSubmit={(event) => { event.preventDefault(); if (!loading) void search() }} aria-busy={loading} className="mt-8">
        <label htmlFor="field-lookup-plate" className="mb-2 block text-sm font-medium">{t('field.report.plate')}</label>
        <input
          id="field-lookup-plate"
          autoFocus
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase())}
          aria-describedby={error ? 'lookup-error' : undefined}
          placeholder={t('field.lookup.platePlaceholder')}
          className="plate-mono min-h-16 w-full rounded-md border border-border-strong bg-bg-raised px-4 py-4 text-2xl text-text-primary placeholder:text-text-tertiary focus-visible:outline-2 focus-visible:outline-accent"
        />
        {error && <p id="lookup-error" role="alert" className="mt-3 rounded-md bg-sev-critical/10 p-3 text-sm text-sev-critical">{error}</p>}
        <div className="mt-5 grid grid-cols-[minmax(0,1fr)_auto] gap-3">
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="flex min-h-12 items-center justify-center gap-2 rounded-md bg-accent px-4 py-3 text-base font-semibold text-on-accent hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50"
          >
            <Search size={20} aria-hidden="true" />
            {loading ? t('field.lookup.checking') : t('field.lookup.lookUp')}
          </button>
          <button
            type="button"
            onClick={resetDraft}
            className="min-h-12 rounded-md border border-border-strong bg-bg-raised px-4 py-3 text-sm font-medium text-text-secondary hover:bg-bg-hover focus-visible:outline-2 focus-visible:outline-accent"
          >
            {t('field.lookup.clear')}
          </button>
        </div>
      </form>
    </section>
  )
}
