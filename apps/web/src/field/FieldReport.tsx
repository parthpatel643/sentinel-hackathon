import { useRef, useState } from 'react'
import { Camera as CameraIcon, CheckCircle2, MapPin } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { enqueueSighting } from './outbox'
import { useOutboxSync } from './sync'

/** docs/03-UX-DESIGN.md §5.3: "camera capture + auto plate read + GPS,
 * queued offline and synced when connectivity returns."
 *
 * Two honest simplifications from the ideal spec, both because they'd
 * need capability this build doesn't have yet:
 * - Camera capture uses `<input capture="environment">`, which hands off
 *   to the device's native camera app rather than a custom in-page
 *   getUserMedia preview — simpler, and it works offline (no camera
 *   stream to manage), which matters more here than a bespoke UI.
 * - "Auto plate read" would mean running the ANPR pipeline on-device;
 *   the actual pipeline is a Python/ONNX process on the edge worker, not
 *   something a browser can run today, so the plate field is manual
 *   entry here, not silently faked as automatic. */
export function FieldReport() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const [plateText, setPlateText] = useState(searchParams.get('plate') ?? '')
  const [notes, setNotes] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null)
  const [gps, setGps] = useState<{ lat: number; lon: number } | null>(null)
  const [gpsError, setGpsError] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { drainNow, refreshPendingCount } = useOutboxSync()

  function captureGps() {
    setGpsError(null)
    if (!navigator.geolocation) {
      setGpsError(t('field.report.gpsUnavailable'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setGps({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => setGpsError(t('field.report.gpsError')),
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  function onPhotoSelected(file: File | null) {
    setPhoto(file)
    setPhotoPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return file ? URL.createObjectURL(file) : null
    })
  }

  async function submit() {
    if (saving || !plateText.trim()) return
    setSaving(true)
    setError(null)
    try {
    const clientReportId = crypto.randomUUID()
    await enqueueSighting({
      clientReportId,
      plateText: plateText.trim(),
      lat: gps?.lat ?? null,
      lon: gps?.lon ?? null,
      notes: notes.trim() || null,
      photoBlob: photo,
      queuedAt: new Date().toISOString(),
      attempts: 0,
      lastError: null,
    })
    await refreshPendingCount()
    window.dispatchEvent(new Event('sentinel:outbox-changed'))
    setSubmitted(true)
    // Try to sync immediately — if we're online this clears the queue in
    // the background right away; if not, it's already safely queued and
    // the next reconnect (or the periodic tick) will pick it up.
    void drainNow().finally(() => window.dispatchEvent(new Event('sentinel:outbox-changed')))
    } catch {
      setError(t('management:saveError'))
    } finally {
      setSaving(false)
    }
  }

  function reset() {
    setPlateText('')
    setNotes('')
    onPhotoSelected(null)
    setGps(null)
    setSubmitted(false)
    setGpsError(null)
    setError(null)
  }

  if (submitted) {
    return (
      <div className="field-report-success flex min-h-full flex-col items-center justify-center gap-4 p-6 text-center">
        <CheckCircle2 size={56} className="text-ok" aria-hidden="true" />
        <h1 className="text-2xl font-semibold text-text-primary">{t('field.report.queued')}</h1>
        <p className="text-sm text-text-secondary">{t('management:reportReady')}</p>
        <p role="status" className="max-w-sm text-sm leading-relaxed text-text-secondary">{t('field.report.willSync')}</p>
        <button onClick={reset} className="mt-4 min-h-12 w-full rounded-md border border-border-strong bg-bg-raised px-5 py-3 text-sm font-medium text-text-primary hover:bg-bg-hover focus-visible:outline-2 focus-visible:outline-accent">
          {t('field.report.reportAnother')}
        </button>
      </div>
    )
  }

  return (
    <section className="field-page field-report" aria-labelledby="report-heading">
      <header className="field-page-heading">
      <h1 id="report-heading" className="text-2xl font-semibold tracking-tight">{t('field.report.submit')}</h1>
      <p>{t('management:offlineReport')}</p>
      </header>
      <form className="field-report-form" onSubmit={(event) => { event.preventDefault(); void submit() }}>
      <fieldset className="field-report-vehicle">
      <legend>{t('management:vehicleDetails')}</legend>
      <div>
        <label htmlFor="report-plate" className="mb-2 block text-sm font-medium text-text-primary">{t('field.report.plate')}</label>
        <input
          id="report-plate"
          autoCapitalize="characters"
          autoComplete="off"
          spellCheck={false}
          value={plateText}
          onChange={(e) => setPlateText(e.target.value.toUpperCase())}
          placeholder={t('field.report.platePlaceholder')}
          className="plate-mono min-h-12 w-full rounded-md border border-border-strong bg-bg-raised px-4 py-3 text-xl text-text-primary placeholder:text-text-tertiary focus-visible:outline-2 focus-visible:outline-accent"
        />
      </div>
      <div className="mt-5">
        <label htmlFor="report-notes" className="mb-2 block text-sm font-medium text-text-primary">{t('field.report.notes')}</label>
        <textarea
          id="report-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={4}
          className="w-full resize-y rounded-md border border-border-strong bg-bg-raised px-4 py-3 text-base leading-relaxed text-text-primary placeholder:text-text-tertiary focus-visible:outline-2 focus-visible:outline-accent"
          placeholder={t('field.report.notesPlaceholder')}
        />
      </div>
      </fieldset>

      <fieldset className="field-report-evidence">
      <legend>{t('management:supportingEvidence')}</legend>
      <p className="field-evidence-help">{t('management:evidenceHelp')}</p>
      <div className="grid gap-5 sm:grid-cols-2">
      <div>
        <label htmlFor="report-photo" className="mb-2 block text-sm font-medium text-text-primary">{t('field.report.photo')}</label>
        <input
          id="report-photo"
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(e) => onPhotoSelected(e.target.files?.[0] ?? null)}
        />
        {photoPreviewUrl ? (
          <button type="button" aria-label={t('field.report.takePhoto')} onClick={() => fileInputRef.current?.click()} className="block w-full overflow-hidden rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
            <img src={photoPreviewUrl} alt={t('field.report.capturedSighting')} className="h-40 w-full object-cover" />
          </button>
        ) : (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex min-h-28 w-full flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border-strong bg-bg-raised px-4 py-5 text-sm font-medium text-text-secondary hover:bg-bg-hover focus-visible:outline-2 focus-visible:outline-accent"
          >
            <CameraIcon size={24} className="text-accent" aria-hidden="true" />
            {t('field.report.takePhoto')}
          </button>
        )}
      </div>

      <div>
        <p id="report-location-label" className="mb-2 text-sm font-medium text-text-primary">{t('field.report.location')}</p>
        <button
          type="button"
          onClick={captureGps}
          aria-describedby={gpsError ? 'report-gps-error' : 'report-location-label'}
          className="flex min-h-12 w-full items-center justify-center gap-2 rounded-md border border-border-strong bg-bg-raised px-4 py-3 text-sm font-medium text-text-secondary hover:bg-bg-hover focus-visible:outline-2 focus-visible:outline-accent sm:min-h-28 sm:flex-col"
        >
          <MapPin size={22} className="shrink-0 text-accent" aria-hidden="true" />
          {gps ? `${gps.lat.toFixed(4)}, ${gps.lon.toFixed(4)}` : t('field.report.captureLocation')}
        </button>
        {gpsError && <p id="report-gps-error" role="alert" className="mt-2 text-sm text-sev-critical">{gpsError}</p>}
      </div>
      </div>
      </fieldset>
      <div className="field-report-submit">
      {error && <p role="alert" className="text-sm text-sev-critical">{error}</p>}
      <button
        type="submit"
        disabled={saving || !plateText.trim()}
        className="min-h-12 rounded-md bg-accent px-4 py-3 text-base font-semibold text-on-accent hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50"
      >
        {saving ? t('management:savingReport') : t('field.report.submit')}
      </button>
      </div>
      </form>
    </section>
  )
}
