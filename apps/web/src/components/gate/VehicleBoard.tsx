import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Check, ChevronRight, Clock } from 'lucide-react'
import { alertsApi } from '../../lib/api'
import { cn } from '../../lib/cn'
import { formatIstDate, formatIstTime } from '../../lib/time'
import { severityForAlert, type VehicleGroup } from '../../lib/vehicles'
import type { Camera } from '../../lib/types'
import { cameraLabel } from '../../lib/cameraStatusColor'

export const VEHICLE_COLUMNS = '78px 124px 116px minmax(150px, 1fr) 48px 92px 82px 136px'

/** Acknowledges every unseen hit in a vehicle group: one decision, one click. */
export async function acknowledgeGroup(group: VehicleGroup) {
  await Promise.all(group.alerts.filter((a) => a.status === 'new').map((a) => alertsApi.update(a.id, { status: 'acknowledged' })))
}

export function CameraTimeCell({ iso }: { iso: string | null }) {
  const { t, i18n } = useTranslation()
  if (!iso) {
    return <div className="gb-c-time gb-cell-time"><span className="gb-t gb-t-unknown"><Clock className="gb-ico gb-s" aria-hidden="true" />{t('gate:timeUnknown')}</span></div>
  }
  return (
    <div className="gb-c-time gb-cell-time">
      <span className="gb-d">{formatIstDate(iso, i18n.language, { day: 'numeric', month: 'short' })} · IST</span>
      <time className="gb-t" dateTime={iso}>{formatIstTime(iso, i18n.language)}</time>
    </div>
  )
}

export function PriorityTag({ score }: { score: number }) {
  const { t } = useTranslation()
  const severity = severityForAlert({ priority_score: score })
  return <span className={cn('gb-crit', severity !== 'critical' && `gb-${severity}`)}>{t(`severity.${severity}`)}</span>
}

interface VehicleBoardRowsProps {
  groups: VehicleGroup[]
  cameras: Camera[] | null
  selectedPlate?: string | null
  onSelect?: (plate: string) => void
  onChanged: () => void
  /** Overview links rows into Alerts; Alerts selects them in place. */
  hrefFor?: (group: VehicleGroup) => string
}

export function VehicleBoardRows({ groups, cameras, selectedPlate, onSelect, onChanged, hrefFor }: VehicleBoardRowsProps) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState<string | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const cameraName = (id: string) => {
    const camera = cameras?.find((c) => c.camera_id === id)
    return camera ? cameraLabel(camera) : id
  }

  async function acknowledge(group: VehicleGroup) {
    setBusy(group.plate)
    setFailed(null)
    try {
      await acknowledgeGroup(group)
      onChanged()
    } catch {
      setFailed(group.plate)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div role="list">
      {groups.map((group) => {
        const lit = group.unseen > 0
        const selected = group.plate === selectedPlate
        const lead = group.lead
        const state = lit ? t('gate:stateNew') : ['resolved', 'false_positive'].includes(lead.status) ? t('gate:stateClosed') : t('gate:stateWorking')
        const label = `${group.plate} · ${state} · ${cameraName(lead.camera_id)}`
        const open = () => onSelect?.(group.plate)
        return (
          <div role="listitem" key={group.plate} className={cn('gb-board-grid gb-board-row', lit && 'gb-new', selected && 'gb-selected', group.timeUnknown && 'gb-sunk')} style={{ ['--cols' as string]: VEHICLE_COLUMNS }}>
            <div className="gb-lamp-cell gb-cell-lamp"><span className="gb-lamp" aria-hidden="true" />{state}</div>
            <CameraTimeCell iso={group.lastCameraTime} />
            <div className="gb-cell-plate">
              {hrefFor
                ? <Link className="gb-plate gb-row-link" to={hrefFor(group)} aria-label={label}>{group.plate}</Link>
                : <button type="button" className="gb-plate gb-row-link" aria-pressed={selected} aria-label={label} onClick={open}>{group.plate}</button>}
            </div>
            <div className="gb-c-cam gb-cell-cam">
              <span className="gb-nm gb-one-line" title={cameraName(lead.camera_id)}>{cameraName(lead.camera_id)}</span>
              <span className="gb-id">{group.cameraIds.length > 1 ? t('gate:multiCamera', { count: group.cameraIds.length }) : lead.camera_id}</span>
            </div>
            <div className="gb-c-num gb-cell-hits">{group.hits}<span className="gb-mobile-unit">{t('gate:hitNoun', { count: group.hits })}</span></div>
            <div className="gb-c-num gb-cell-sight">{group.sightings}</div>
            <div className="gb-cell-prio"><PriorityTag score={group.priorityScore} /></div>
            <div className="gb-c-act gb-cell-act">
              {lit
                ? <button type="button" className="gb-btn gb-sm" disabled={busy === group.plate} onClick={() => acknowledge(group)}>
                    <Check className="gb-ico gb-s" aria-hidden="true" />{busy === group.plate ? t('gate:acknowledging') : t('gate:acknowledge')}
                  </button>
                : hrefFor
                  ? <Link className="gb-btn gb-sm gb-ghost" to={hrefFor(group)}>{t('gate:open')}<ChevronRight className="gb-ico gb-s" aria-hidden="true" /></Link>
                  : <button type="button" className="gb-btn gb-sm gb-ghost" onClick={open}>{t('gate:open')}<ChevronRight className="gb-ico gb-s" aria-hidden="true" /></button>}
            </div>
            {group.timeUnknown && (
              <div className="gb-reason">
                <strong>{t('gate:timeUnknown')} — {t('gate:timeUnknownReason')}</strong>
                <span>{t('gate:timeUnknownRanked')}</span>
                <Link to={`/cameras?camera=${encodeURIComponent(lead.camera_id)}`}>{t('gate:checkCamera', { camera: lead.camera_id })}</Link>
              </div>
            )}
            {failed === group.plate && <p role="alert" className="gb-reason gb-reason-error">{t('gate:updateFailed')}</p>}
          </div>
        )
      })}
    </div>
  )
}

export function VehicleBoardHead() {
  const { t } = useTranslation()
  return (
    <div className="gb-board-grid gb-board-head" style={{ ['--cols' as string]: VEHICLE_COLUMNS }} aria-hidden="true">
      <div>{t('gate:colStatus')}</div>
      <div>{t('gate:colLastSeen')} <span className="gb-unit">IST</span></div>
      <div>{t('gate:colPlate')}</div>
      <div>{t('gate:colCamera')}</div>
      <div className="gb-num">{t('gate:colHits')}</div>
      <div className="gb-num">{t('gate:colSightings')}</div>
      <div>{t('gate:colPriority')}</div>
      <div className="gb-num">{t('gate:colAction')}</div>
    </div>
  )
}
