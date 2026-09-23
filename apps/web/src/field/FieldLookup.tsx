import { useState } from 'react'
import { CheckCircle2, Search, ShieldAlert } from 'lucide-react'
import { fieldApi } from '../lib/api'
import { ApiError } from '../lib/http'
import type { PlateLookup } from '../lib/types'

const STATUS_LABEL: Record<string, string> = {
  clear: 'Clear',
  stolen_vehicle: 'Stolen vehicle',
  wanted_vehicle: 'Wanted vehicle',
  missing_person: 'Missing person',
  suspect: 'Suspect vehicle',
  bolo: 'Be on the lookout',
}

/** docs/03-UX-DESIGN.md §5.2: "result shows the vehicle's status (clear /
 * stolen / wanted) as a full-screen colour-and-icon verdict readable at
 * arm's length in sunlight." A big plate input (native mobile keyboards
 * already handle alphanumeric entry well one-handed — a fully custom
 * on-screen keypad wasn't worth the extra complexity here) rather than a
 * literal numeric-only keypad, since Indian plates mix letters and digits. */
export function FieldLookup() {
  const [input, setInput] = useState('')
  const [result, setResult] = useState<PlateLookup | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function search() {
    if (!input.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      setResult(await fieldApi.lookup(input.trim()))
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : 'Could not reach the server.')
    } finally {
      setLoading(false)
    }
  }

  if (result) {
    const isClear = result.status === 'clear'
    return (
      <div
        className={`flex h-full flex-col items-center justify-center gap-4 p-6 text-center ${
          isClear ? 'bg-ok/15' : 'bg-sev-critical/15'
        }`}
      >
        {isClear ? (
          <CheckCircle2 size={72} className="text-ok" />
        ) : (
          <ShieldAlert size={72} className="text-sev-critical" />
        )}
        <p className="plate-mono text-3xl font-bold text-text-primary">{result.plate_normalised}</p>
        <p className={`text-2xl font-semibold ${isClear ? 'text-ok' : 'text-sev-critical'}`}>
          {isClear ? 'Clear' : STATUS_LABEL[result.status] ?? result.status}
        </p>
        {result.last_seen_at && (
          <p className="text-sm text-text-secondary">
            Last seen {new Date(result.last_seen_at).toLocaleString()}
            {result.last_seen_camera_name && ` at ${result.last_seen_camera_name}`}
          </p>
        )}
        {!result.last_seen_at && <p className="text-sm text-text-tertiary">No sightings on file.</p>}
        <button
          onClick={() => {
            setResult(null)
            setInput('')
          }}
          className="mt-4 rounded-full bg-bg-raised px-6 py-3 text-sm font-medium text-text-primary"
        >
          Look up another plate
        </button>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-6">
      <p className="text-sm text-text-tertiary">Enter a plate to check its status</p>
      <input
        autoFocus
        value={input}
        onChange={(e) => setInput(e.target.value.toUpperCase())}
        onKeyDown={(e) => e.key === 'Enter' && search()}
        placeholder="GJ 01 AB 1234"
        className="plate-mono w-full max-w-xs rounded-xl border border-border-subtle bg-bg-inset px-4 py-4 text-center text-2xl text-text-primary placeholder:text-text-tertiary"
      />
      <button
        onClick={search}
        disabled={loading || !input.trim()}
        className="flex w-full max-w-xs items-center justify-center gap-2 rounded-xl bg-accent py-4 text-base font-semibold text-white disabled:opacity-50"
      >
        <Search size={20} />
        {loading ? 'Checking…' : 'Look up'}
      </button>
      {error && <p className="text-sm text-sev-critical">{error}</p>}
    </div>
  )
}
