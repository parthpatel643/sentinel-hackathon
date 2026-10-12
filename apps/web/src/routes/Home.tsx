import { useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, RefreshCw, Search } from 'lucide-react'
import { alertsApi, detectionsApi } from '../lib/api'
import { useJurisdiction } from '../lib/jurisdiction'
import { usePolling } from '../lib/usePolling'
import { useLiveEvents } from '../lib/liveEvents'
import { groupAlertsByVehicle } from '../lib/vehicles'
import { DISTRICT_COUNT, rollupByDistrict } from '../lib/districts'
import { formatIst } from '../lib/time'
import { TopBar } from '../components/layout/TopBar'
import { RequestError } from '../components/ui/RequestError'
import { SealedClipModal } from '../components/SealedClipModal'
import { VehicleBoardHead, VehicleBoardRows } from '../components/gate/VehicleBoard'
import { SightingPass } from '../components/gate/SightingPass'
import { DistrictBoard } from '../components/gate/DistrictBoard'
import type { EvidenceClip } from '../lib/types'
import './command-overview.css'

const DISTRICT_PREVIEW = 6
const DISTRICT_COLUMNS = 'minmax(0, 1fr) 46px minmax(64px, 96px) minmax(104px, auto)'

export function Home() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { cameras, camerasError, refreshCameras, inScope } = useJurisdiction()
  const { data: alerts, error: alertsError, refetch: refreshAlerts } = usePolling(() => alertsApi.list('new'), 20000)
  const { data: activity, error: activityError, refetch: refreshActivity } = usePolling(() => detectionsApi.activity(60), 15000)
  useLiveEvents((kind) => { if (kind === 'alert') refreshAlerts() })
  const [selectedPlate, setSelectedPlate] = useState<string | null>(null)
  const [viewingClip, setViewingClip] = useState<EvidenceClip | null>(null)
  const [plate, setPlate] = useState('')

  const scopedCameras = useMemo(() => (cameras ?? []).filter((c) => inScope(c.camera_id)), [cameras, inScope])
  const scopedAlerts = useMemo(() => (alerts ?? []).filter((a) => inScope(a.camera_id)), [alerts, inScope])
  const groups = useMemo(() => groupAlertsByVehicle(scopedAlerts), [scopedAlerts])
  // Counted by the API per camera over the last hour, summed here for the
  // jurisdiction. Vehicles are distinct registrations per camera, so a
  // vehicle seen at two cameras is two sightings. Reads are not listed.
  const anpr = useMemo(() => {
    const rows = (activity ?? []).filter((a) => inScope(a.camera_id))
    return {
      reads: rows.reduce((n, a) => n + a.reads, 0),
      vehicles: rows.reduce((n, a) => n + a.vehicles, 0),
      cameras: rows.length,
      latest: rows.reduce<string | null>((latest, a) => (!latest || a.last_read_at > latest ? a.last_read_at : latest), null),
    }
  }, [activity, inScope])
  const districts = useMemo(() => rollupByDistrict(scopedCameras), [scopedCameras])
  const counts = {
    live: scopedCameras.filter((c) => c.status === 'live').length,
    down: scopedCameras.filter((c) => c.status === 'down').length,
    degraded: scopedCameras.filter((c) => c.status === 'degraded').length,
    unknown: scopedCameras.filter((c) => c.status === 'unknown').length,
    stale: scopedCameras.filter((c) => c.status === 'stale').length,
    connecting: scopedCameras.filter((c) => c.status === 'connecting').length,
  }
  const selected = groups.find((g) => g.plate === selectedPlate) ?? groups[0]

  function investigate(event: FormEvent) {
    event.preventDefault()
    if (plate.trim()) navigate(`/find-a-vehicle?plate=${encodeURIComponent(plate.trim())}`)
  }
  const refreshAll = () => { refreshCameras(); refreshAlerts(); refreshActivity() }
  const summaryValue = (value: number) => (camerasError ? t('common.notAvailable') : cameras ? value : t('common.loading'))

  return (
    <div className="gb-overview">
      <TopBar title={t('workspace.overviewTitle')} titleKey="workspace.overviewTitle" subtitle={t('gate:pageNote')} actions={
        <button type="button" className="gb-btn" aria-label={t('workspace.refreshOverview')} onClick={refreshAll}>
          <RefreshCw className="gb-ico" aria-hidden="true" />{t('workspace.refresh')}
        </button>
      } />
      <div className="gb-page">
        <section className="gb-netline gb-overview-net" aria-label={t('workspace.summary')}>
          <span>{t('gate:summaryCameras')}</span>
          <Link to="/cameras" aria-label={t('workspace.registeredCameras')}><b>{summaryValue(scopedCameras.length)}</b>{t('workspace.registeredCameras').toLowerCase()}</Link>
          <Link to="/live-wall" aria-label={t('workspace.liveCameras')}>{counts.live > 0 && <span className="gb-glyph gb-live" aria-hidden="true" />}<b>{summaryValue(counts.live)}</b>{t('cameraStatus.live').toLowerCase()}</Link>
          <Link to="/cameras" aria-label={t('workspace.interruptedCameras')}>{counts.down + counts.degraded > 0 && <span className="gb-glyph gb-down" aria-hidden="true" />}<b>{summaryValue(counts.down + counts.degraded)}</b>{t('workspace.interruptedCameras').toLowerCase()}</Link>
          <Link to="/cameras" aria-label={t('cameraStatus.unknown')}>{counts.unknown > 0 && <span className="gb-glyph gb-unknown" aria-hidden="true" />}<b>{summaryValue(counts.unknown)}</b>{t('cameraStatus.unknown').toLowerCase()}</Link>
          {counts.stale + counts.connecting > 0 && <span className="gb-quiet">{t('gate:notReporting', { stale: counts.stale, connecting: counts.connecting })}</span>}
          <Link to="/alerts" aria-label={t('workspace.queuedAlerts')}><b>{alertsError ? t('common.notAvailable') : alerts ? scopedAlerts.length : t('common.loading')}</b>{t('gate:hitNoun', { count: scopedAlerts.length })} · {t('gate:vehicles', { count: groups.length })}</Link>
        </section>
        {Boolean(camerasError) && <RequestError onRetry={refreshCameras} />}
        {cameras?.length === 0 && !camerasError && (
          <div className="gb-empty"><b>{t('workspace.noCameras')}</b><Link to="/cameras" className="gb-btn gb-sm">{t('cameras.addCamera')}<ArrowRight className="gb-ico gb-s" aria-hidden="true" /></Link></div>
        )}

        <div className="gb-split">
          <div className="gb-stack">
            <section className="gb-board gb-order-board" aria-labelledby="watchlist-board">
              <div className="gb-board-top">
                <h2 id="watchlist-board" className="gb-board-title">{t('gate:watchlistBoard')}</h2>
                <span className="gb-tally"><b>{scopedAlerts.length}</b>{t('gate:hitNoun', { count: scopedAlerts.length })}<span className="gb-sep">·</span><b>{groups.length}</b>{t('gate:vehicleNoun', { count: groups.length })}</span>
                <span className="gb-board-note">{t('gate:onePerVehicle')}</span>
                <span className="gb-spacer" />
                <span className="gb-key-new">{t('gate:litKey')}</span>
              </div>
              {Boolean(alertsError) && <div className="px-4 pb-3"><RequestError onRetry={refreshAlerts} /></div>}
              {!alerts && !alertsError && <p className="gb-board-foot">{t('common.loading')}</p>}
              {alerts && groups.length === 0 && !alertsError && <div className="gb-empty"><b>{t('gate:nothingWaiting')}</b><span>{t('gate:nothingWaitingHelp')}</span></div>}
              {groups.length > 0 && <>
                <VehicleBoardHead />
                <VehicleBoardRows groups={groups.slice(0, 6)} cameras={cameras} selectedPlate={selected?.plate} onSelect={setSelectedPlate} onChanged={refreshAlerts} />
              </>}
              <div className="gb-board-foot">
                <span>{t('gate:showing', { shown: Math.min(groups.length, 6), total: groups.length, hits: scopedAlerts.length })}</span>
                <Link to="/alerts"><span>{t('gate:openQueue')}</span><ArrowRight className="gb-ico gb-s" aria-hidden="true" /></Link>
              </div>
            </section>

            <div className="gb-row-2 gb-order-lower">
              <section className="gb-board gb-activity-board" aria-labelledby="anpr-heading">
                <div className="gb-board-top">
                  <h2 id="anpr-heading" className="gb-board-title gb-s">{t('gate:anprActivity')}</h2>
                  <span className="gb-tally"><b>{activity ? anpr.vehicles : '—'}</b>{t('gate:vehicleSightings', { count: anpr.vehicles })}</span>
                </div>
                {Boolean(activityError) && <div className="px-4 pb-3"><RequestError onRetry={refreshActivity} /></div>}
                {activity && !activityError && (anpr.reads === 0
                  ? <p className="gb-detect-note">{t('gate:noReadsYet')}</p>
                  : <>
                      <dl className="gb-activity">
                        <div><dt>{t('gate:plateReads')}</dt><dd><b>{anpr.reads}</b></dd></div>
                        <div><dt>{t('gate:camerasReading')}</dt><dd><b>{anpr.cameras}</b>{t('gate:ofLive', { count: counts.live })}</dd></div>
                        <div><dt>{t('gate:latestReadLabel')}</dt><dd>{anpr.latest ? formatIst(anpr.latest, i18n.language) : '—'}</dd></div>
                      </dl>
                      <p className="gb-detect-note">{t('gate:onlyRegistrations')}</p>
                    </>)}
                <div className="gb-board-foot">
                  <span />
                  <Link to="/find-a-vehicle"><span>{t('gate:searchPlate')}</span><ArrowRight className="gb-ico gb-s" aria-hidden="true" /></Link>
                </div>
              </section>

              <section className="gb-board" aria-labelledby="district-heading">
                <div className="gb-board-top">
                  <h2 id="district-heading" className="gb-board-title gb-s">{t('gate:camerasByDistrict')}</h2>
                  <span className="gb-spacer" />
                  <span className="gb-board-note">{t('gate:districtsWithCameras', { count: districts.filter((d) => d.district).length, total: DISTRICT_COUNT })}</span>
                </div>
                <div className="gb-board-grid gb-board-head" style={{ ['--cols' as string]: DISTRICT_COLUMNS }} aria-hidden="true">
                  <div>{t('gate:colDistrict')}</div><div className="gb-num">{t('gate:colCams')}</div><div>{t('gate:colMix')}</div><div>{t('gate:colProblem')}</div>
                </div>
                <DistrictBoard rows={districts.slice(0, DISTRICT_PREVIEW)} columns={DISTRICT_COLUMNS} compact />
                {districts.length > DISTRICT_PREVIEW && <p className="gb-board-foot gb-quiet">{t('gate:moreDistricts', { count: districts.length - DISTRICT_PREVIEW })}</p>}
                <div className="gb-board-foot">
                  <span>{t('gate:totals', { total: scopedCameras.length, live: counts.live, down: counts.down, unknown: counts.unknown })}</span>
                  <Link to="/cameras"><span>{t('gate:openCameras')}</span><ArrowRight className="gb-ico gb-s" aria-hidden="true" /></Link>
                </div>
              </section>
            </div>
          </div>

          <div className="gb-stack gb-sticky">
            <form className="gb-board gb-trace gb-order-trace" onSubmit={investigate} aria-label={t('command:quickInvestigation')}>
              <h2 className="gb-board-title gb-s">{t('workspace.startInvestigation')}</h2>
              <p className="gb-sub">{t('gate:searchHelp')}</p>
              <div className="gb-field-row">
                <label className="gb-field gb-plate-field">
                  <Search className="gb-ico" aria-hidden="true" />
                  <span className="gb-sr">{t('workspace.plate')}</span>
                  <input id="overview-plate" value={plate} onChange={(e) => setPlate(e.target.value)} placeholder="GJ 01 AB 1234" autoComplete="off" spellCheck={false} required />
                </label>
                <button type="submit" className="gb-btn gb-primary">{t('command:traceVehicle')}</button>
              </div>
            </form>
            {selected
              ? <div className="gb-order-pass"><SightingPass group={selected} cameras={cameras} onChanged={refreshAlerts} onViewClip={setViewingClip} /></div>
              : alerts && <div className="gb-empty gb-pass-empty gb-order-pass"><b>{t('gate:pass')}</b><span>{t('gate:selectVehicle')}</span></div>}
          </div>
        </div>
      </div>
      <SealedClipModal clip={viewingClip} onClose={() => setViewingClip(null)} />
    </div>
  )
}
