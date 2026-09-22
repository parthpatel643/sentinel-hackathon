import { CheckCircle2, Compass, FileUp, Link2, Radar, Server } from 'lucide-react'
import { useEffect, useState } from 'react'
import { camerasApi, departmentsApi } from '../lib/api'
import { ApiError } from '../lib/http'
import type { BulkImportResult, Camera, CameraCreate, CameraStream, Department } from '../lib/types'
import { HlsVideoPlayer } from './HlsVideoPlayer'
import { MapView, type MapMarker } from './MapView'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Input } from './ui/Input'
import { Modal } from './ui/Modal'

type Step = 'location' | 'connect' | 'bulk-import' | 'discover' | 'analytics' | 'success'

const TIER_CHOICES: { tier: string; label: string; detail: string }[] = [
  {
    tier: 'a_continuous',
    label: 'Read number plates continuously',
    detail: 'Traffic junctions, check-posts, high-value sites — analysed every frame.',
  },
  {
    tier: 'b_sampled',
    label: 'Watch, but sample to save bandwidth',
    detail: 'General coverage cameras — analysed a few times a second.',
  },
  {
    tier: 'c_motion_gated',
    label: 'Only watch when something moves',
    detail: 'Low-traffic areas, godowns, offices — idle until motion, then samples.',
  },
]

interface OnboardingWizardProps {
  open: boolean
  onClose: () => void
  onOnboarded: () => void
}

/** The Cameras screen's "Add camera" action — a three-step, plain-language
 * wizard (docs/03-UX-DESIGN.md §4.6), not a raw form: *Where is it?* / *How
 * do we connect?* / *What should it watch for?*. "How do we connect?"
 * branches into whichever onboarding path the operator actually has
 * (a direct link, a CSV, or the department catalogue) rather than assuming
 * everyone is typing an RTSP URL by hand. */
export function OnboardingWizard({ open, onClose, onOnboarded }: OnboardingWizardProps) {
  const [step, setStep] = useState<Step>('location')
  const [departments, setDepartments] = useState<Department[]>([])

  // Step 1 — Where is it?
  const [name, setName] = useState('')
  const [departmentName, setDepartmentName] = useState('')
  const [siteName, setSiteName] = useState('')
  const [pin, setPin] = useState<{ lat: number; lon: number } | null>(null)
  const [facingDegrees, setFacingDegrees] = useState(0)

  // Step 2 — How do we connect? ("I have a link" path)
  const [protocol, setProtocol] = useState('rtsp')
  const [url, setUrl] = useState('')

  // Step 3 — What should it watch for?
  const [tier, setTier] = useState('b_sampled')

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createdCamera, setCreatedCamera] = useState<Camera | null>(null)
  const [preview, setPreview] = useState<CameraStream | null>(null)

  // Bulk import sub-flow
  const [file, setFile] = useState<File | null>(null)
  const [dryRunResult, setDryRunResult] = useState<BulkImportResult | null>(null)
  const [importBusy, setImportBusy] = useState(false)

  // Department-system discovery sub-flow
  const [discoverResult, setDiscoverResult] = useState<Record<string, unknown> | null>(null)
  const [discovering, setDiscovering] = useState(false)

  useEffect(() => {
    if (open) departmentsApi.list().then(setDepartments).catch(() => {})
  }, [open])

  function reset() {
    setStep('location')
    setName('')
    setDepartmentName('')
    setSiteName('')
    setPin(null)
    setFacingDegrees(0)
    setProtocol('rtsp')
    setUrl('')
    setTier('b_sampled')
    setError(null)
    setCreatedCamera(null)
    setPreview(null)
    setFile(null)
    setDryRunResult(null)
    setDiscoverResult(null)
  }

  function handleClose() {
    reset()
    onClose()
  }

  const markers: MapMarker[] = pin
    ? [{ id: 'pin', lat: pin.lat, lon: pin.lon, color: 'oklch(0.68 0.16 245)' }]
    : []

  async function submitLinkCamera() {
    setSubmitting(true)
    setError(null)
    try {
      const cameraId = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || crypto.randomUUID()
      const payload: CameraCreate = {
        camera_id: cameraId,
        name: name.trim(),
        driver_id: protocol,
        department_name: departmentName || null,
        site_name: siteName || null,
        location: pin,
        tier,
        profiles: url ? [{ protocol, url }] : [],
        attributes: facingDegrees ? { facing_degrees: String(facingDegrees) } : {},
      }
      const camera = await camerasApi.create(payload)
      setCreatedCamera(camera)
      try {
        setPreview(await camerasApi.stream(camera.camera_id))
      } catch {
        setPreview({ available: false, hls_url: null, reason: 'Could not check the live preview.' })
      }
      setStep('success')
      onOnboarded()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : 'Could not create this camera.')
    } finally {
      setSubmitting(false)
    }
  }

  async function runDryRun() {
    if (!file) return
    setImportBusy(true)
    setError(null)
    try {
      setDryRunResult(await camerasApi.bulkImport(file, true))
    } catch {
      setError('Could not read this file. Check it is a CSV with the expected columns.')
    } finally {
      setImportBusy(false)
    }
  }

  async function commitImport() {
    if (!file) return
    setImportBusy(true)
    setError(null)
    try {
      setDryRunResult(await camerasApi.bulkImport(file, false))
      onOnboarded()
    } catch {
      setError('Import failed — nothing was committed.')
    } finally {
      setImportBusy(false)
    }
  }

  async function runDiscovery() {
    setDiscovering(true)
    setError(null)
    try {
      setDiscoverResult(await camerasApi.discover())
      onOnboarded()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : 'Could not reach the department catalogue.')
    } finally {
      setDiscovering(false)
    }
  }

  const titleByStep: Record<Step, string> = {
    location: 'Add a camera — where is it?',
    connect: 'Add a camera — how do we connect?',
    'bulk-import': 'Import cameras from a file',
    discover: 'Connect a department system',
    analytics: 'Add a camera — what should it watch for?',
    success: 'Camera added',
  }

  return (
    <Modal open={open} onOpenChange={(next) => !next && handleClose()} title={titleByStep[step]}>
      <div className="flex flex-col gap-4">
        {step !== 'success' && step !== 'bulk-import' && step !== 'discover' && (
          <div className="flex items-center gap-2 text-xs text-text-tertiary">
            {(['location', 'connect', 'analytics'] as const).map((s, i) => (
              <span key={s} className="flex items-center gap-2">
                <span
                  className={
                    s === step
                      ? 'flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[11px] font-semibold text-white'
                      : 'flex h-5 w-5 items-center justify-center rounded-full bg-bg-inset text-[11px]'
                  }
                >
                  {i + 1}
                </span>
                {i < 2 && <span className="h-px w-6 bg-border-subtle" />}
              </span>
            ))}
          </div>
        )}

        {step === 'location' && (
          <div className="flex flex-col gap-3">
            <Input
              autoFocus
              placeholder="Camera name (e.g. Sarkhej Circle North)"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <div className="grid grid-cols-2 gap-3">
              <select
                value={departmentName}
                onChange={(e) => setDepartmentName(e.target.value)}
                className="h-10 rounded-md border border-border-subtle bg-bg-inset px-3 text-sm text-text-primary"
              >
                <option value="">No department</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.name}>
                    {d.name}
                  </option>
                ))}
              </select>
              <Input placeholder="Site (optional)" value={siteName} onChange={(e) => setSiteName(e.target.value)} />
            </div>
            <p className="text-xs text-text-tertiary">Click the map to drop a pin where this camera is mounted.</p>
            <div className="relative h-64 overflow-hidden rounded-md border border-border-subtle">
              <MapView
                markers={markers}
                className="absolute inset-0"
                onMapClick={(lat, lon) => setPin({ lat, lon })}
              />
            </div>
            {pin && (
              <div className="flex items-center gap-3 text-xs text-text-secondary">
                <span className="plate-mono">
                  {pin.lat.toFixed(4)}, {pin.lon.toFixed(4)}
                </span>
                <label className="flex items-center gap-2">
                  <Compass size={14} className="text-text-tertiary" />
                  Facing
                  <input
                    type="range"
                    min={0}
                    max={359}
                    value={facingDegrees}
                    onChange={(e) => setFacingDegrees(Number(e.target.value))}
                  />
                  <span className="plate-mono w-9">{facingDegrees}°</span>
                </label>
              </div>
            )}
            <div className="flex justify-end">
              <Button disabled={!name.trim()} onClick={() => setStep('connect')}>
                Next
              </Button>
            </div>
          </div>
        )}

        {step === 'connect' && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <Card
                className="flex cursor-pointer flex-col items-center gap-2 border-accent/40 bg-accent/10 p-4 text-center"
                onClick={() => {}}
              >
                <Link2 size={20} className="text-accent" />
                <p className="text-sm font-medium text-text-primary">I have a link</p>
                <p className="text-xs text-text-tertiary">RTSP, HLS or WHEP URL</p>
              </Card>
              <Card
                className="flex cursor-pointer flex-col items-center gap-2 p-4 text-center hover:border-accent/40"
                onClick={() => setStep('bulk-import')}
              >
                <FileUp size={20} className="text-text-tertiary" />
                <p className="text-sm font-medium text-text-primary">Import a file</p>
                <p className="text-xs text-text-tertiary">CSV of many cameras at once</p>
              </Card>
              <Card
                className="flex cursor-pointer flex-col items-center gap-2 p-4 text-center hover:border-accent/40"
                onClick={() => setStep('discover')}
              >
                <Server size={20} className="text-text-tertiary" />
                <p className="text-sm font-medium text-text-primary">Connect a department system</p>
                <p className="text-xs text-text-tertiary">Sync from the department catalogue</p>
              </Card>
              <Card className="flex flex-col items-center gap-2 p-4 text-center opacity-50">
                <Radar size={20} className="text-text-tertiary" />
                <p className="text-sm font-medium text-text-primary">Discover on my network</p>
                <p className="text-xs text-text-tertiary">Not available in this build yet</p>
              </Card>
            </div>
            <div className="flex flex-col gap-2 rounded-md border border-border-subtle p-3">
              <p className="text-xs font-medium text-text-secondary">Stream link</p>
              <div className="flex gap-2">
                <select
                  value={protocol}
                  onChange={(e) => setProtocol(e.target.value)}
                  className="h-10 w-28 rounded-md border border-border-subtle bg-bg-inset px-2 text-sm text-text-primary"
                >
                  <option value="rtsp">RTSP</option>
                  <option value="hls">HLS</option>
                  <option value="whep">WHEP</option>
                </select>
                <Input
                  className="flex-1 plate-mono"
                  placeholder="rtsp://192.168.1.20:554/stream1"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                />
              </div>
            </div>
            {error && <p className="text-xs text-sev-critical">{error}</p>}
            <div className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep('location')}>
                Back
              </Button>
              <Button onClick={() => setStep('analytics')}>Next</Button>
            </div>
          </div>
        )}

        {step === 'analytics' && (
          <div className="flex flex-col gap-3">
            {TIER_CHOICES.map((choice) => (
              <label
                key={choice.tier}
                className={
                  tier === choice.tier
                    ? 'flex cursor-pointer items-start gap-3 rounded-md border border-accent bg-accent/10 p-3'
                    : 'flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle p-3 hover:border-accent/40'
                }
              >
                <input
                  type="radio"
                  className="mt-1"
                  checked={tier === choice.tier}
                  onChange={() => setTier(choice.tier)}
                />
                <div>
                  <p className="text-sm font-medium text-text-primary">{choice.label}</p>
                  <p className="text-xs text-text-tertiary">{choice.detail}</p>
                </div>
              </label>
            ))}
            {error && <p className="text-xs text-sev-critical">{error}</p>}
            <div className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep('connect')}>
                Back
              </Button>
              <Button disabled={submitting} onClick={submitLinkCamera}>
                {submitting ? 'Adding…' : 'Add camera'}
              </Button>
            </div>
          </div>
        )}

        {step === 'bulk-import' && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-text-secondary">
              CSV columns: <span className="plate-mono">camera_id, name</span> required;{' '}
              <span className="plate-mono">department_name, site_name, lat, lon, tier, protocol, url, codec</span>{' '}
              optional.
            </p>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null)
                setDryRunResult(null)
              }}
              className="text-sm text-text-secondary"
            />
            {!dryRunResult && (
              <Button disabled={!file || importBusy} onClick={runDryRun}>
                {importBusy ? 'Checking…' : 'Preview (dry run)'}
              </Button>
            )}
            {dryRunResult && (
              <>
                <Card className="max-h-64 overflow-y-auto p-3 text-xs">
                  <p className="mb-2 font-medium text-text-primary">
                    {dryRunResult.succeeded} of {dryRunResult.total_rows} row(s) valid
                    {dryRunResult.dry_run ? ' (dry run — nothing saved yet)' : ' — imported'}
                  </p>
                  <table className="w-full text-left">
                    <tbody>
                      {dryRunResult.rows.map((row) => (
                        <tr key={row.row_number} className="border-t border-border-subtle/60">
                          <td className="py-1 pr-2">#{row.row_number}</td>
                          <td className="py-1 pr-2 plate-mono">{row.camera_id ?? '—'}</td>
                          <td className={row.ok ? 'py-1 text-ok' : 'py-1 text-sev-critical'}>
                            {row.ok ? 'OK' : row.error}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
                {dryRunResult.dry_run && dryRunResult.succeeded > 0 && (
                  <Button disabled={importBusy} onClick={commitImport}>
                    {importBusy ? 'Importing…' : `Import ${dryRunResult.succeeded} camera(s)`}
                  </Button>
                )}
                {!dryRunResult.dry_run && (
                  <p className="text-sm text-ok">Import committed — cameras are now in the registry.</p>
                )}
              </>
            )}
            {error && <p className="text-xs text-sev-critical">{error}</p>}
            <div className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep('connect')}>
                Back
              </Button>
              <Button variant="ghost" onClick={handleClose}>
                Done
              </Button>
            </div>
          </div>
        )}

        {step === 'discover' && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-text-secondary">
              Fetches the department catalogue right now and onboards every camera it lists — no manual entry
              needed once your department's credentials are configured.
            </p>
            {!discoverResult && (
              <Button disabled={discovering} onClick={runDiscovery}>
                {discovering ? 'Syncing…' : 'Sync now'}
              </Button>
            )}
            {discoverResult && (
              <Card className="p-3 text-sm text-text-secondary">
                <pre className="whitespace-pre-wrap text-xs">{JSON.stringify(discoverResult, null, 2)}</pre>
              </Card>
            )}
            {error && <p className="text-xs text-sev-critical">{error}</p>}
            <div className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep('connect')}>
                Back
              </Button>
              <Button variant="ghost" onClick={handleClose}>
                Done
              </Button>
            </div>
          </div>
        )}

        {step === 'success' && createdCamera && (
          <div className="flex flex-col items-center gap-3 py-2 text-center">
            <CheckCircle2 size={28} className="text-ok" />
            <p className="text-sm font-medium text-text-primary">{createdCamera.name} was added</p>
            <div className="aspect-video w-full overflow-hidden rounded-md bg-bg-inset">
              {preview?.available && preview.hls_url ? (
                <HlsVideoPlayer src={preview.hls_url} className="h-full w-full" />
              ) : (
                <div className="flex h-full items-center justify-center p-4 text-center text-xs text-text-tertiary">
                  {preview?.reason ?? 'Checking live preview…'}
                </div>
              )}
            </div>
            <Button onClick={handleClose}>Done</Button>
          </div>
        )}
      </div>
    </Modal>
  )
}
