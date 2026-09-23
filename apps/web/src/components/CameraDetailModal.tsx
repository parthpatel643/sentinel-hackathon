import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { camerasApi, zonesApi } from '../lib/api'
import type { Camera, CameraStream, Zone, ZoneEvent } from '../lib/types'
import { HlsVideoPlayer } from './HlsVideoPlayer'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'
import { SeverityBadge, statusToSeverity } from './ui/SeverityBadge'
import { useAuth } from '../lib/AuthContext'
import { hasCurrentFrameRate } from '../lib/cameraStatusColor'
import { VideoOff } from 'lucide-react'
import '../routes/monitoring-workspace.css'

const PRESET_REGIONS: { key: string; polygon: number[][] }[] = [
  { key: 'fullFrame', polygon: [[0, 0], [1, 0], [1, 1], [0, 1]] },
  { key: 'leftHalf', polygon: [[0, 0], [0.5, 0], [0.5, 1], [0, 1]] },
  { key: 'rightHalf', polygon: [[0.5, 0], [1, 0], [1, 1], [0.5, 1]] },
  { key: 'topHalf', polygon: [[0, 0], [1, 0], [1, 0.5], [0, 0.5]] },
  { key: 'bottomHalf', polygon: [[0, 0.5], [1, 0.5], [1, 1], [0, 1]] },
  { key: 'centreThird', polygon: [[0.33, 0.33], [0.67, 0.33], [0.67, 0.67], [0.33, 0.67]] },
]

const RULE_TYPES = ['intrusion', 'loitering', 'wrong_way', 'stopped_vehicle'] as const

interface CameraDetailModalProps {
  camera: Camera | null
  onClose: () => void
}

function fpsLabel(camera: Camera): string {
  if (!hasCurrentFrameRate(camera)) return '—'
  const declared = camera.declared_fps != null ? `/${camera.declared_fps.toFixed(0)}` : ''
  return `${camera.measured_fps!.toFixed(1)}${declared} fps`
}

/** M13 secondary analytics: zone rules for this camera. A preset-region
 * picker rather than a draw-your-own-polygon canvas — the rule *engine*
 * (edge_agent.analytics.zone_rules) accepts any polygon; this is a
 * deliberately simple configuration surface on top of it, not a
 * limitation of what the engine itself can express. */
function ZoneRulesSection({ camera }: { camera: Camera }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [zones, setZones] = useState<Zone[] | null>(null)
  const [events, setEvents] = useState<ZoneEvent[] | null>(null)
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [ruleType, setRuleType] = useState<(typeof RULE_TYPES)[number]>(RULE_TYPES[0])
  const [presetIndex, setPresetIndex] = useState(0)
  const [error, setError] = useState<string | null>(null)

  function load() {
    zonesApi.list(camera.camera_id).then(setZones).catch(() => setError(t('monitoring:zoneLoadError')))
    zonesApi.events(camera.camera_id).then(setEvents).catch(() => setError(t('monitoring:zoneLoadError')))
  }

  useEffect(load, [camera.camera_id]) // eslint-disable-line react-hooks/exhaustive-deps

  function createZone() {
    if (!name.trim()) return
    setError(null)
    zonesApi
      .create(camera.camera_id, {
        name: name.trim(),
        rule_type: ruleType,
        polygon: PRESET_REGIONS[presetIndex].polygon,
      })
      .then(() => {
        setName('')
        setAdding(false)
        load()
      })
      .catch(() => setError(t('cameraDetail.zoneRules.createError')))
  }

  return (
    <section className="camera-zone-section flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-text-primary">{t('cameraDetail.zoneRules.title')}</h2>
        {user?.role === 'admin' && (
          <Button size="sm" variant="secondary" onClick={() => setAdding((v) => !v)}>
            {adding ? t('cameraDetail.zoneRules.cancel') : t('cameraDetail.zoneRules.addZone')}
          </Button>
        )}
      </div>

      {adding && (
        <div className="flex flex-col gap-2 rounded-md bg-bg-inset p-3">
          <input
            aria-label={t('monitoring:zoneName')}
            className="rounded-md border border-border-subtle bg-bg-base px-2.5 py-1.5 text-sm text-text-primary"
            placeholder={t('cameraDetail.zoneRules.namePlaceholder')}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <div className="flex gap-2">
            <select
              aria-label={t('monitoring:zoneType')}
              className="flex-1 rounded-md border border-border-subtle bg-bg-base px-2.5 py-1.5 text-sm text-text-primary"
              value={ruleType}
              onChange={(e) => setRuleType(e.target.value as (typeof RULE_TYPES)[number])}
            >
              {RULE_TYPES.map((r) => (
                <option key={r} value={r}>
                  {t(`cameraDetail.zoneRules.ruleTypes.${r}`)}
                </option>
              ))}
            </select>
            <select
              aria-label={t('monitoring:zoneRegion')}
              className="flex-1 rounded-md border border-border-subtle bg-bg-base px-2.5 py-1.5 text-sm text-text-primary"
              value={presetIndex}
              onChange={(e) => setPresetIndex(Number(e.target.value))}
            >
              {PRESET_REGIONS.map((r, i) => (
                <option key={r.key} value={i}>
                  {t(`cameraDetail.zoneRules.presets.${r.key}`)}
                </option>
              ))}
            </select>
          </div>
          <Button size="sm" onClick={createZone}>
            {t('cameraDetail.zoneRules.create')}
          </Button>
        </div>
      )}
      {error && <p role="alert" className="text-xs text-sev-critical">{error}</p>}

      {zones && zones.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {zones.map((z) => (
            <li key={z.id} className="flex items-center justify-between rounded-md bg-bg-inset px-3 py-1.5">
              <span className="text-text-primary">{z.name}</span>
              <span className="text-xs text-text-tertiary">{z.rule_type}</span>
            </li>
          ))}
        </ul>
      )}
      {zones && zones.length === 0 && !adding && (
        <p className="text-xs text-text-tertiary">{t('cameraDetail.zoneRules.noZones')}</p>
      )}

      {events && events.length > 0 && (
        <div>
          <p className="mb-1 text-xs uppercase tracking-wide text-text-tertiary">
            {t('cameraDetail.zoneRules.recentEvents')}
          </p>
          <ul className="flex flex-col gap-1 text-xs text-text-secondary">
            {events.slice(0, 5).map((e) => (
              <li key={e.id}>
                {new Date(e.observed_at).toLocaleTimeString()} — {e.zone_name ?? e.zone_id} (
                {e.rule_type}
                {e.dwell_time_s != null ? `, ${e.dwell_time_s.toFixed(0)}s` : ''})
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

/** The Cameras screen's "click a camera, see it" moment. Never asks for or
 * touches a raw stream URL itself — that would mean handling gov-catalogue
 * credentials in the browser, which core_api's /stream endpoint exists
 * specifically to avoid (see registry/service.py's resolve_camera_stream).
 * A camera outside our own local relay is reported as unavailable with a
 * plain-language reason instead of silently failing. */
export function CameraDetailModal({ camera, onClose }: CameraDetailModalProps) {
  const { t } = useTranslation()
  const [stream, setStream] = useState<CameraStream | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!camera) {
      setStream(null)
      return
    }
    setLoading(true)
    setStream(null)
    let cancelled = false
    camerasApi
      .stream(camera.camera_id)
      .then((value) => { if (!cancelled) setStream(value) })
      .catch(() => { if (!cancelled) setStream({ available: false, hls_url: null, reason: t('cameraDetail.couldNotReachApi') }) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [camera, t])

  return (
    <Modal open={camera !== null} onOpenChange={(open) => !open && onClose()} title={camera?.name ?? ''}>
      {camera && (
        <div className="camera-detail-workspace">
          <div className="camera-detail-status flex flex-wrap items-center gap-3 text-sm">
            <SeverityBadge severity={statusToSeverity(camera.status)} label={t(`cameraStatus.${camera.status}`)} />
            <span className="text-text-tertiary">{camera.camera_id}</span>
            {camera.department_name && <span className="text-text-secondary">{camera.department_name}</span>}
            <span className="plate-mono text-text-secondary">{fpsLabel(camera)}</span>
          </div>

          <div className="camera-detail-main">
          <section className="camera-detail-preview">
          <h2>{t('monitoring:connection')}</h2>
          <div className="monitoring-video aspect-video w-full overflow-hidden rounded-md">
            {loading && (
              <div className="flex h-full items-center justify-center text-sm text-text-tertiary">
                {t('cameraDetail.checkingStream')}
              </div>
            )}
            {!loading && stream?.available && stream.hls_url && (
              <HlsVideoPlayer src={stream.hls_url} className="h-full w-full" />
            )}
            {!loading && stream && (!stream.available || !stream.hls_url) && (
              <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
                <VideoOff size={30} strokeWidth={1.5} />
                <strong>{t('monitoring:unavailable')}</strong>
                <p className="text-sm">{stream.reason ?? t('cameraDetail.liveUnavailable')}</p>
              </div>
            )}
          </div>
          <p className="monitoring-help">{t('monitoring:streamHelp')}</p>
          </section>
          <section className="camera-detail-information">
          <h2>{t('monitoring:information')}</h2>
          <dl>
            <div><dt>{t('monitoring:department')}</dt><dd>{camera.department_name ?? t('common.unknown')}</dd></div>
            <div><dt>{t('monitoring:site')}</dt><dd>{camera.site_name ?? t('common.unknown')}</dd></div>
            <div>
              <dt className="text-text-tertiary">{t('cameraDetail.tier')}</dt>
              <dd className="text-text-primary">{camera.tier}</dd>
            </div>
            <div>
              <dt className="text-text-tertiary">{t('cameraDetail.reconnects')}</dt>
              <dd className="text-text-primary">{camera.reconnects}</dd>
            </div>
            <div>
              <dt className="text-text-tertiary">{t('cameraDetail.source')}</dt>
              <dd className="text-text-primary">{camera.source ?? t('common.unknown')}</dd>
            </div>
            <div>
              <dt className="text-text-tertiary">{t('cameraDetail.lastSeen')}</dt>
              <dd className="text-text-primary">
                {camera.last_seen_at ? new Date(camera.last_seen_at).toLocaleString() : t('common.unknown')}
              </dd>
            </div>
          </dl>
          </section>
          </div>
          <ZoneRulesSection key={camera.camera_id} camera={camera} />
        </div>
      )}
    </Modal>
  )
}
