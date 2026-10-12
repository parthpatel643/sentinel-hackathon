import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Check, CheckCheck, ScanLine, Search, X } from 'lucide-react'
import { alertsApi } from '../../lib/api'
import { cameraLabel } from '../../lib/cameraStatusColor'
import { formatIst } from '../../lib/time'
import { useSnapshot } from '../../lib/useSnapshot'
import type { Camera, EvidenceClip } from '../../lib/types'
import type { VehicleGroup } from '../../lib/vehicles'
import { ClipAction } from './ClipAction'
import { PriorityTag, acknowledgeGroup } from './VehicleBoard'
import { StatusWord } from './StatusWord'

function EvidenceFrame({ group, camera }: { group: VehicleGroup; camera: string }) {
  const { t } = useTranslation()
  const snapshot = useSnapshot(group.lead.detection_event_id)
  return (
    <figure className="gb-evidence">
      {snapshot.status === 'ready'
        ? <img src={snapshot.url} alt={t('gate:evidenceAlt', { camera, plate: group.plate })} />
        : <div className="gb-evidence-empty"><ScanLine className="gb-ico gb-l" aria-hidden="true" /><span>{snapshot.status === 'loading' ? t('common.loading') : t(snapshot.status === 'failed' ? 'gate:evidenceFailed' : 'gate:evidenceMissing')}</span></div>}
      <figcaption>{t('gate:evidence')} · {group.lead.camera_id} · {group.lastCameraTime ? formatIst(group.lastCameraTime, undefined, { second: '2-digit' }) : t('gate:timeUnknown')}</figcaption>
    </figure>
  )
}

interface SightingPassProps {
  group: VehicleGroup
  cameras: Camera[] | null
  onChanged: () => void
  onViewClip: (clip: EvidenceClip) => void
  /** Alerts shows the frame and the full decision set; Overview keeps it short. */
  detailed?: boolean
  children?: ReactNode
}

export function SightingPass({ group, cameras, onChanged, onViewClip, detailed = false, children }: SightingPassProps) {
  const { t, i18n } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const lead = group.lead
  const camera = cameras?.find((c) => c.camera_id === lead.camera_id)
  const cameraName = camera ? cameraLabel(camera) : lead.camera_id
  const lit = group.unseen > 0
  const closed = group.alerts.every((a) => ['resolved', 'false_positive'].includes(a.status))

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(false)
    try {
      await action()
      onChanged()
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }
  const closeAll = (status: 'resolved' | 'false_positive') => () =>
    Promise.all(group.alerts.filter((a) => !['resolved', 'false_positive'].includes(a.status)).map((a) => alertsApi.update(a.id, { status })))

  return (
    <section className="gb-pass" aria-label={t('investigation:selectedAlert')}>
      <header className="gb-pass-head">
        <h2>{t('gate:pass')}</h2>
        <span className="gb-pass-kind">{t('gate:passKind', { count: group.hits })}</span>
        <span className="gb-spacer" />
        {lit ? <span className="gb-chip-new">{t('gate:stateNew')}</span> : <span className="gb-badge">{t(closed ? 'gate:stateClosed' : 'gate:stateWorking')}</span>}
      </header>
      <div className="gb-pass-plate">
        <div className="min-w-0">
          <div className="gb-lbl">{t('gate:passPlate')}</div>
          <div className="gb-plate gb-xl">{group.plate}</div>
        </div>
        <div className="text-right">
          <div className="gb-lbl">{t('gate:readConfidence')}</div>
          <div className="gb-fig gb-l">{Math.round(lead.match_confidence * 100)}%</div>
        </div>
      </div>
      {detailed && <div className="gb-pass-frame"><EvidenceFrame group={group} camera={cameraName} /></div>}
      <div className="gb-perf" aria-hidden="true" />
      <div className="gb-pass-grid" style={{ ['--n' as string]: 2 }}>
        <div className="gb-cell">
          <div className="gb-lbl">{t('gate:camera')}</div>
          <div className="gb-val"><span className="gb-data">{lead.camera_id}</span> · {cameraName}</div>
          <div className="gb-sub">{camera ? <StatusWord status={camera.status} /> : t('gate:unavailable')}{group.cameraIds.length > 1 && ` · ${t('gate:multiCamera', { count: group.cameraIds.length })}`}</div>
        </div>
        <div className="gb-cell">
          <div className="gb-lbl">{t('gate:lastSeen')}</div>
          <div className="gb-val">{group.lastCameraTime ? `${formatIst(group.lastCameraTime, i18n.language)} IST` : t('gate:timeUnknown')}</div>
          <div className="gb-sub">{group.lastCameraTime ? t('gate:fromCameraClock') : t('gate:timeUnknownReason')}</div>
        </div>
      </div>
      <div className="gb-pass-grid" style={{ ['--n' as string]: 4 }}>
        <div className="gb-cell"><div className="gb-lbl">{t('gate:hits')}</div><div className="gb-val gb-fig">{group.hits}</div></div>
        <div className="gb-cell"><div className="gb-lbl">{t('gate:sightings')}</div><div className="gb-val gb-fig">{group.sightings}</div></div>
        <div className="gb-cell"><div className="gb-lbl">{t('gate:match')}</div><div className="gb-val">{t(lead.match_rung === 'exact' ? 'gate:exact' : 'gate:probable')}</div><div className="gb-sub">{t('gate:onWatchlistSub')}</div></div>
        <div className="gb-cell"><div className="gb-lbl">{t('gate:priority')}</div><div className="gb-val"><PriorityTag score={group.priorityScore} /></div></div>
      </div>
      {children}
      <div className="gb-perf" aria-hidden="true" />
      <div className="gb-stub">
        <div>
          <div className="gb-lbl">{t('gate:reference')}</div>
          <div className="gb-ref-stub" aria-label={lead.watchlist_entry_id}>{lead.watchlist_entry_id.split('-').map((part, i) => <span key={i} aria-hidden="true">{part}</span>)}</div>
        </div>
        <div className="gb-pass-actions">
          {lit && <button type="button" className="gb-btn gb-primary" disabled={busy} onClick={() => run(() => acknowledgeGroup(group))}><Check className="gb-ico" aria-hidden="true" />{busy ? t('gate:acknowledging') : t('alerts.acknowledge')}</button>}
          {detailed && !closed && <button type="button" className={lit ? 'gb-btn' : 'gb-btn gb-primary'} disabled={busy} onClick={() => run(closeAll('resolved'))}><CheckCheck className="gb-ico" aria-hidden="true" />{t('alerts.resolve')}</button>}
          <Link className="gb-btn" to={`/find-a-vehicle?plate=${encodeURIComponent(group.plate)}`}><Search className="gb-ico" aria-hidden="true" />{t('gate:investigate')}</Link>
          <ClipAction alert={lead} onView={onViewClip} />
        </div>
        {!detailed && <Link className="gb-not-this" to={`/alerts?alert=${encodeURIComponent(lead.id)}`}>{t('gate:openInAlerts')}</Link>}
        {detailed && !closed && (
          <button type="button" className="gb-not-this" disabled={busy} onClick={() => run(closeAll('false_positive'))}>
            <X className="gb-ico gb-s" aria-hidden="true" />{t('gate:notThisVehicle')}
          </button>
        )}
        {error && <p role="alert" className="gb-pass-error">{t('investigation:updateFailed')}</p>}
      </div>
    </section>
  )
}
