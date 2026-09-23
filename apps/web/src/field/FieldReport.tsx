import { useRef, useState } from 'react'
import { Camera as CameraIcon, CheckCircle2, MapPin } from 'lucide-react'
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
  const [plateText, setPlateText] = useState('')
  const [notes, setNotes] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null)
  const [gps, setGps] = useState<{ lat: number; lon: number } | null>(null)
  const [gpsError, setGpsError] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { drainNow, refreshPendingCount } = useOutboxSync()

  function captureGps() {
    setGpsError(null)
    if (!navigator.geolocation) {
      setGpsError('GPS is not available on this device.')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setGps({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => setGpsError('Could not get a GPS fix — check location permissions.'),
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
    setSubmitted(true)
    // Try to sync immediately — if we're online this clears the queue in
    // the background right away; if not, it's already safely queued and
    // the next reconnect (or the periodic tick) will pick it up.
    drainNow()
  }

  function reset() {
    setPlateText('')
    setNotes('')
    onPhotoSelected(null)
    setGps(null)
    setSubmitted(false)
  }

  if (submitted) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
        <CheckCircle2 size={64} className="text-ok" />
        <p className="text-lg font-semibold text-text-primary">Report queued</p>
        <p className="text-sm text-text-tertiary">
          It will sync automatically the moment you have a connection.
        </p>
        <button onClick={reset} className="mt-4 rounded-full bg-bg-raised px-6 py-3 text-sm font-medium text-text-primary">
          Report another sighting
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div>
        <label className="mb-1.5 block text-xs font-medium text-text-tertiary">Plate</label>
        <input
          value={plateText}
          onChange={(e) => setPlateText(e.target.value.toUpperCase())}
          placeholder="GJ 01 AB 1234"
          className="plate-mono w-full rounded-xl border border-border-subtle bg-bg-inset px-4 py-3.5 text-lg text-text-primary placeholder:text-text-tertiary"
        />
      </div>

      <div>
        <label className="mb-1.5 block text-xs font-medium text-text-tertiary">Photo</label>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(e) => onPhotoSelected(e.target.files?.[0] ?? null)}
        />
        {photoPreviewUrl ? (
          <button onClick={() => fileInputRef.current?.click()} className="block w-full overflow-hidden rounded-xl">
            <img src={photoPreviewUrl} alt="Captured sighting" className="h-40 w-full object-cover" />
          </button>
        ) : (
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex h-24 w-full flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-border-subtle text-sm text-text-tertiary"
          >
            <CameraIcon size={22} />
            Take a photo
          </button>
        )}
      </div>

      <div>
        <label className="mb-1.5 block text-xs font-medium text-text-tertiary">Location</label>
        <button
          onClick={captureGps}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-border-subtle bg-bg-inset py-3 text-sm font-medium text-text-secondary"
        >
          <MapPin size={16} />
          {gps ? `${gps.lat.toFixed(4)}, ${gps.lon.toFixed(4)}` : 'Capture my location'}
        </button>
        {gpsError && <p className="mt-1 text-xs text-sev-critical">{gpsError}</p>}
      </div>

      <div>
        <label className="mb-1.5 block text-xs font-medium text-text-tertiary">Notes (optional)</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          className="w-full rounded-xl border border-border-subtle bg-bg-inset px-4 py-3 text-sm text-text-primary placeholder:text-text-tertiary"
          placeholder="Direction of travel, occupants, anything else…"
        />
      </div>

      <button
        onClick={submit}
        disabled={!plateText.trim()}
        className="rounded-xl bg-accent py-4 text-base font-semibold text-white disabled:opacity-50"
      >
        Submit sighting
      </button>
    </div>
  )
}
