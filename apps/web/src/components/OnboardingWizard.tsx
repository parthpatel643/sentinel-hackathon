import { CheckCircle2, Compass, FileUp, Link2, Server } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { camerasApi, departmentsApi } from '../lib/api'
import { ApiError } from '../lib/http'
import type { BulkImportResult, Camera, CameraCreate, CameraStream, Department } from '../lib/types'
import { HlsVideoPlayer } from './HlsVideoPlayer'
import { MapView, type MapMarker } from './MapView'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Input } from './ui/Input'
import { Modal } from './ui/Modal'
import '../routes/monitoring-workspace.css'

type Step = 'location' | 'connect' | 'bulk-import' | 'discover' | 'analytics' | 'success'

const TIER_CHOICES = ['continuous', 'sampled', 'motionGated'] as const
const TIER_VALUE: Record<(typeof TIER_CHOICES)[number], string> = {
  continuous: 'a_continuous',
  sampled: 'b_sampled',
  motionGated: 'c_motion_gated',
}

interface OnboardingWizardProps {
  open: boolean
  onClose: () => void
  onOnboarded: () => void
  initialStep?: 'location' | 'bulk-import' | 'discover'
}

/** The Cameras screen's "Add camera" action — a three-step, plain-language
 * wizard (docs/03-UX-DESIGN.md §4.6), not a raw form: *Where is it?* / *How
 * do we connect?* / *What should it watch for?*. "How do we connect?"
 * branches into whichever onboarding path the operator actually has
 * (a direct link, a CSV, or the department catalogue) rather than assuming
 * everyone is typing an RTSP URL by hand. */
export function OnboardingWizard({ open, onClose, onOnboarded, initialStep = 'location' }: OnboardingWizardProps) {
  const { t } = useTranslation()
  const [step, setStep] = useState<Step>(initialStep)
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
    setStep(initialStep)
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
        setPreview({ available: false, hls_url: null, reason: t('onboarding.previewCheckFailed') })
      }
      setStep('success')
      onOnboarded()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : t('onboarding.createError'))
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
      setError(t('onboarding.readFileError'))
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
      setError(t('onboarding.importFailed'))
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
      setError(err instanceof ApiError ? String(err.detail) : t('onboarding.discoverError'))
    } finally {
      setDiscovering(false)
    }
  }

  const titleByStep: Record<Step, string> = {
    location: t('onboarding.titles.location'),
    connect: t('onboarding.titles.connect'),
    'bulk-import': t('onboarding.titles.bulkImport'),
    discover: t('onboarding.titles.discover'),
    analytics: t('onboarding.titles.analytics'),
    success: t('onboarding.titles.success'),
  }

  return (
    <Modal open={open} onOpenChange={(next) => !next && handleClose()} title={titleByStep[step]}>
      <div className="camera-onboarding">
        <aside className="onboarding-guide">
          <h2>{t('cameras.addCamera')}</h2>
          <p>{t('monitoring:onboardingHelp')}</p>
        {step !== 'success' && step !== 'bulk-import' && step !== 'discover' && (
          <ol className="onboarding-steps">
            {(['location', 'connect', 'analytics'] as const).map((s, i) => (
              <li key={s} aria-current={s === step ? 'step' : undefined}><span>{i + 1}</span><strong>{t(`monitoring:${s}Step`)}</strong></li>
            ))}
          </ol>
        )}
        {(step === 'bulk-import' || step === 'discover') && <div className="onboarding-path-icon">{step === 'bulk-import' ? <FileUp size={32} /> : <Server size={32} />}<strong>{t(step === 'bulk-import' ? 'monitoring:importCameras' : 'monitoring:discoverCameras')}</strong></div>}
        </aside>
        <div className="onboarding-form">
        {step === 'location' && (
          <div className="flex flex-col gap-3">
            <label className="monitoring-field-label" htmlFor="onboarding-name">{t('monitoring:name')}</label>
            <Input
              id="onboarding-name"
              autoFocus
              placeholder={t('onboarding.namePlaceholder')}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <div className="onboarding-field-pair">
              <label className="monitoring-field-label">{t('monitoring:department')}
              <select
                value={departmentName}
                onChange={(e) => setDepartmentName(e.target.value)}
                className="h-10 rounded-md border border-border-subtle bg-bg-inset px-3 text-sm text-text-primary"
              >
                <option value="">{t('onboarding.noDepartment')}</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.name}>
                    {d.name}
                  </option>
                ))}
              </select>
              </label>
              <label className="monitoring-field-label">{t('monitoring:site')}
              <Input
                placeholder={t('onboarding.sitePlaceholder')}
                value={siteName}
                onChange={(e) => setSiteName(e.target.value)}
              />
              </label>
            </div>
            <p className="text-xs text-text-tertiary">{t('onboarding.clickMapToPin')}</p>
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
                  {t('onboarding.facing')}
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
                {t('onboarding.next')}
              </Button>
            </div>
          </div>
        )}

        {step === 'connect' && (
          <div className="flex flex-col gap-3">
            <div className="onboarding-connection-options">
              <div className="onboarding-connection-choice" data-active="true">
                <Link2 size={20} className="text-accent" />
                <p className="text-sm font-medium text-text-primary">{t('onboarding.connectOptions.haveLink')}</p>
                <p className="text-xs text-text-tertiary">{t('onboarding.connectOptions.haveLinkDetail')}</p>
              </div>
              <button type="button"
                className="onboarding-connection-choice"
                onClick={() => setStep('bulk-import')}
              >
                <FileUp size={20} className="text-text-tertiary" />
                <p className="text-sm font-medium text-text-primary">{t('onboarding.connectOptions.importFile')}</p>
                <p className="text-xs text-text-tertiary">{t('onboarding.connectOptions.importFileDetail')}</p>
              </button>
              <button type="button"
                className="onboarding-connection-choice"
                onClick={() => setStep('discover')}
              >
                <Server size={20} className="text-text-tertiary" />
                <p className="text-sm font-medium text-text-primary">{t('onboarding.connectOptions.connectDept')}</p>
                <p className="text-xs text-text-tertiary">{t('onboarding.connectOptions.connectDeptDetail')}</p>
              </button>
            </div>
            <div className="flex flex-col gap-2 rounded-md border border-border-subtle p-3">
              <label htmlFor="onboarding-stream" className="text-xs font-medium text-text-secondary">{t('onboarding.streamLink')}</label>
              <div className="flex gap-2">
                <select
                  aria-label={t('monitoring:protocol')}
                  value={protocol}
                  onChange={(e) => setProtocol(e.target.value)}
                  className="h-10 w-28 rounded-md border border-border-subtle bg-bg-inset px-2 text-sm text-text-primary"
                >
                  <option value="rtsp">RTSP</option>
                  <option value="hls">HLS</option>
                  <option value="whep">WHEP</option>
                </select>
                <Input
                  id="onboarding-stream"
                  className="flex-1 plate-mono"
                  placeholder={t('onboarding.urlPlaceholder')}
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                />
              </div>
            </div>
            {error && <p className="text-xs text-sev-critical">{error}</p>}
            <div className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep('location')}>
                {t('onboarding.back')}
              </Button>
              <Button onClick={() => setStep('analytics')}>{t('onboarding.next')}</Button>
            </div>
          </div>
        )}

        {step === 'analytics' && (
          <div className="flex flex-col gap-3">
            {TIER_CHOICES.map((choice) => (
              <label
                key={choice}
                className={
                  tier === TIER_VALUE[choice]
                    ? 'flex cursor-pointer items-start gap-3 rounded-md border border-accent bg-accent/10 p-3'
                    : 'flex cursor-pointer items-start gap-3 rounded-md border border-border-subtle p-3 hover:border-accent/40'
                }
              >
                <input
                  type="radio"
                  className="mt-1"
                  checked={tier === TIER_VALUE[choice]}
                  onChange={() => setTier(TIER_VALUE[choice])}
                />
                <div>
                  <p className="text-sm font-medium text-text-primary">{t(`onboarding.tiers.${choice}.label`)}</p>
                  <p className="text-xs text-text-tertiary">{t(`onboarding.tiers.${choice}.detail`)}</p>
                </div>
              </label>
            ))}
            {error && <p className="text-xs text-sev-critical">{error}</p>}
            <div className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep('connect')}>
                {t('onboarding.back')}
              </Button>
              <Button disabled={submitting} onClick={submitLinkCamera}>
                {submitting ? t('onboarding.adding') : t('onboarding.addCamera')}
              </Button>
            </div>
          </div>
        )}

        {step === 'bulk-import' && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-text-secondary">{t('onboarding.bulkImportHelp')}</p>
            <input
              aria-label={t('monitoring:csvFile')}
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
                {importBusy ? t('onboarding.checkingFile') : t('onboarding.previewDryRun')}
              </Button>
            )}
            {dryRunResult && (
              <>
                <Card className="max-h-64 overflow-y-auto p-3 text-xs">
                  <p className="mb-2 font-medium text-text-primary">
                    {t('onboarding.rowsValid', { succeeded: dryRunResult.succeeded, total: dryRunResult.total_rows })}
                    {dryRunResult.dry_run ? t('onboarding.dryRunNotice') : t('onboarding.importedNotice')}
                  </p>
                  <table className="w-full text-left">
                    <tbody>
                      {dryRunResult.rows.map((row) => (
                        <tr key={row.row_number} className="border-t border-border-subtle/60">
                          <td className="py-1 pr-2">#{row.row_number}</td>
                          <td className="py-1 pr-2 plate-mono">{row.camera_id ?? t('common.unknown')}</td>
                          <td className={row.ok ? 'py-1 text-ok' : 'py-1 text-sev-critical'}>
                            {row.ok ? t('onboarding.rowOk') : row.error}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
                {dryRunResult.dry_run && dryRunResult.succeeded > 0 && (
                  <Button disabled={importBusy} onClick={commitImport}>
                    {importBusy ? t('onboarding.importing') : t('onboarding.importCameras', { count: dryRunResult.succeeded })}
                  </Button>
                )}
                {!dryRunResult.dry_run && (
                  <p className="text-sm text-ok">{t('onboarding.importCommitted')}</p>
                )}
              </>
            )}
            {error && <p className="text-xs text-sev-critical">{error}</p>}
            <div className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep('connect')}>
                {t('onboarding.back')}
              </Button>
              <Button variant="ghost" onClick={handleClose}>
                {t('onboarding.done')}
              </Button>
            </div>
          </div>
        )}

        {step === 'discover' && (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-text-secondary">{t('onboarding.discoverHelp')}</p>
            {!discoverResult && (
              <Button disabled={discovering} onClick={runDiscovery}>
                {discovering ? t('onboarding.syncing') : t('onboarding.syncNow')}
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
                {t('onboarding.back')}
              </Button>
              <Button variant="ghost" onClick={handleClose}>
                {t('onboarding.done')}
              </Button>
            </div>
          </div>
        )}

        {step === 'success' && createdCamera && (
          <div className="flex flex-col items-center gap-3 py-2 text-center">
            <CheckCircle2 size={28} className="text-ok" />
            <p className="text-sm font-medium text-text-primary">
              {t('onboarding.cameraAdded', { name: createdCamera.name })}
            </p>
            <div className="aspect-video w-full overflow-hidden rounded-md bg-bg-inset">
              {preview?.available && preview.hls_url ? (
                <HlsVideoPlayer src={preview.hls_url} className="h-full w-full" />
              ) : (
                <div className="flex h-full items-center justify-center p-4 text-center text-xs text-text-tertiary">
                  {preview?.reason ?? t('onboarding.checkingPreview')}
                </div>
              )}
            </div>
            <Button onClick={handleClose}>{t('onboarding.done')}</Button>
          </div>
        )}
        </div>
      </div>
    </Modal>
  )
}
