import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Activity, Camera as CameraIcon, FileUp, LayoutList, List, Map, Plus, RefreshCw, Search, Server } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { camerasApi, coverageApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { TopBar } from '../components/layout/TopBar'
import { Card } from '../components/ui/Card'
import { SeverityBadge, statusToSeverity, tamperToSeverity } from '../components/ui/SeverityBadge'
import { MapView, type MapMarker } from '../components/MapView'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { RequestError } from '../components/ui/RequestError'
import { CameraDetailModal } from '../components/CameraDetailModal'
import { OnboardingWizard } from '../components/OnboardingWizard'
import { CoverageLifecyclePanel } from '../components/CoverageLifecyclePanel'
import { cameraLabel, cameraLabelWithLocality, cameraStatusColor, hasCurrentFrameRate } from '../lib/cameraStatusColor'
import type { Camera } from '../lib/types'
import './monitoring-workspace.css'
import { useAuth } from '../lib/AuthContext'
import { DISTRICT_COUNT, rollupByDistrict } from '../lib/districts'
import { DistrictBoard } from '../components/gate/DistrictBoard'
import { StatusWord } from '../components/gate/StatusWord'

const DISTRICT_COLUMNS = '150px minmax(160px, 1.1fr) 64px 56px 56px 80px minmax(120px, 1.6fr) 40px'
const CAMERA_COLUMNS = 'minmax(96px, .8fr) minmax(160px, 2fr) minmax(120px, 1fr) 64px'

/** Analysis this far behind live means the machine cannot keep up with this
 * camera's tier: lower the sampled rate or move the camera to another worker. */
const LAG_WARNING_S = 5

function fpsLabel(camera: Camera): string {
  if (!hasCurrentFrameRate(camera)) return '—'
  const declared = camera.declared_fps != null ? `/${camera.declared_fps.toFixed(0)}` : ''
  return `${camera.measured_fps!.toFixed(1)}${declared} fps`
}

export function Cameras() {
  const { t } = useTranslation()
  const { data: cameras, loading, error, refetch } = usePolling(() => camerasApi.list(), 10000)
  const { t: tr } = useTranslation('readiness')
  // Registry writes are administrator-only on the API; operators are not
  // offered actions that would be refused.
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [view, setView] = useState<'districts' | 'table' | 'map' | 'insights'>('districts')
  const [openDistrict, setOpenDistrict] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [department, setDepartment] = useState('all')
  const [showGaps, setShowGaps] = useState(false)
  const { data: gapReport } = usePolling(
    () => (showGaps ? coverageApi.gaps() : Promise.resolve(null)),
    60000,
    [showGaps],
  )
  const coverageGaps = useMemo<[number, number][]>(
    () =>
      showGaps
        ? (gapReport?.cells ?? []).filter((cell) => !cell.covered).map((cell) => [cell.center.lon, cell.center.lat])
        : [],
    [showGaps, gapReport],
  )
  const departments = Array.from(
    new Set((cameras ?? []).map((camera) => camera.department_name).filter((name): name is string => Boolean(name))),
  ).sort()
  const [selected, setSelected] = useState<Camera | null>(null)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [onboardingPath, setOnboardingPath] = useState<'location' | 'bulk-import' | 'discover'>('location')
  const [searchParams, setSearchParams] = useSearchParams()

  // Lets the ⌘K palette (and any other deep link) jump straight to a
  // camera's detail modal via /cameras?camera=<id> without duplicating
  // the lookup logic anywhere else.
  useEffect(() => {
    const cameraId = searchParams.get('camera')
    if (!cameraId || !cameras) return
    const match = cameras.find((c) => c.camera_id === cameraId)
    if (match) setSelected(match)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('camera')
      return next
    }, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameras, searchParams])

  const filteredCameras = useMemo(() => cameras?.filter((camera) =>
    (status === 'all' || camera.status === status) &&
    (department === 'all' || camera.department_name === department) &&
    `${camera.name} ${camera.display_name ?? ''} ${camera.camera_id}`.toLowerCase().includes(query.trim().toLowerCase()),
  ), [cameras, status, department, query])
  const markers: MapMarker[] =
    filteredCameras
      ?.filter((c): c is Camera & { location: NonNullable<Camera['location']> } => c.location != null)
      .map((c) => ({
        id: c.camera_id,
        lat: c.location.lat,
        lon: c.location.lon,
        color: cameraStatusColor(c.status),
        label: cameraLabelWithLocality(c),
        onClick: () => setSelected(c),
      })) ?? []

  const districts = useMemo(() => rollupByDistrict(filteredCameras ?? []), [filteredCameras])

  function openOnboarding(path: typeof onboardingPath) {
    setOnboardingPath(path)
    setWizardOpen(true)
  }

  return (
    <div className="monitoring-workspace flex min-h-0 flex-1 flex-col">
      <TopBar
        title={t('nav.cameras')}
        titleKey="nav.cameras"
        subtitle={cameras ? `${t('cameras.registered', { count: cameras.length })} · ${t('monitoring:registryHelp')}` : t('monitoring:registryHelp')}
        actions={isAdmin && <button type="button" className="gb-btn gb-primary" onClick={() => openOnboarding('location')}><Plus className="gb-ico" aria-hidden="true" />{t('cameras.addCamera')}</button>}
      />
      <div className="registry-workspace">
      <div className="registry-health gb-seg" role="group" aria-label={t('workspace.allStatuses')}>
        {['all', 'down', 'degraded', 'stale', 'unknown', 'connecting', 'live'].map((value) => (
          <button key={value} type="button" aria-label={t(`monitoring:${value === 'all' ? 'all' : value}Cameras`)} aria-pressed={status === value} onClick={() => setStatus(value)}>
            {value !== 'all' && <span className={`gb-glyph gb-${value === 'connecting' ? 'idle' : value}`} aria-hidden="true" />}
            <span>{value === 'all' ? t('monitoring:allCameras') : t(`cameraStatus.${value}`)}</span>
            <span className="gb-n">{cameras ? (value === 'all' ? cameras.length : cameras.filter((camera) => camera.status === value).length) : '—'}</span>
          </button>
        ))}
      </div>
      <section className="registry-inventory" aria-label={t('monitoring:registry')}>
      <div className="registry-toolbar">
        <div className="monitoring-search"><Search size={16} /><Input aria-label={t('workspace.filterCameras')} placeholder={t('workspace.filterCameras')} value={query} onChange={(e) => setQuery(e.target.value)} /></div>
        <select aria-label={tr('departmentFilter')} value={department} onChange={(e) => setDepartment(e.target.value)} className="h-11 rounded-md border border-border-strong bg-bg-inset px-3 text-sm">
          <option value="all">{tr('allDepartments')}</option>
          {departments.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <select aria-label={t('workspace.allStatuses')} value={status} onChange={(e) => setStatus(e.target.value)} className="h-11 rounded-md border border-border-strong bg-bg-inset px-3 text-sm">
          <option value="all">{t('workspace.allStatuses')}</option>
          {['live', 'connecting', 'degraded', 'down', 'stale', 'unknown'].map((value) => <option key={value} value={value}>{t(`cameraStatus.${value}`)}</option>)}
        </select>
        <div className="registry-view-switch">
          <div className="segmented" role="group" aria-label={t('cameras.view')}>
            <Button aria-pressed={view === 'districts'} size="sm" variant="ghost" onClick={() => setView('districts')}><LayoutList size={15} />{t('gate:colDistrict')}</Button>
            <Button aria-pressed={view === 'table'} size="sm" variant="ghost" onClick={() => setView('table')}><List size={15} />{t('cameras.table')}</Button>
            <Button aria-pressed={view === 'map'} size="sm" variant="ghost" onClick={() => setView('map')}><Map size={15} />{t('cameras.map')}</Button>
            <Button aria-pressed={view === 'insights'} size="sm" variant="ghost" onClick={() => setView('insights')}><Activity size={15} />{tr('insights')}</Button>
          </div>
          <Button size="sm" variant="ghost" aria-label={t('monitoring:refresh')} onClick={refetch}><RefreshCw size={16} /></Button>
        </div>
      </div>
      <div className="registry-results"><span>{cameras ? t('monitoring:results', { count: filteredCameras?.length ?? 0 }) : t('cameras.loading')}</span>{(query || status !== 'all' || department !== 'all') && <button onClick={() => { setQuery(''); setStatus('all'); setDepartment('all') }}>{t('monitoring:resetFilters')}</button>}</div>
      {Boolean(error) && <div className="p-4"><RequestError onRetry={refetch} /></div>}

      {view === 'districts' ? (
        <div className="registry-districts">
          {loading && !cameras && <p className="gb-board-foot">{t('cameras.loading')}</p>}
          {cameras && filteredCameras?.length === 0 && <div className="gb-empty"><b>{t(cameras.length === 0 ? 'monitoring:noCameras' : 'workspace.noMatchingCameras')}</b></div>}
          {filteredCameras && filteredCameras.length > 0 && <>
            <div className="gb-board-top">
              <h2 className="gb-board-title gb-s">{t('gate:camerasByDistrict')}</h2>
              <span className="gb-board-note">{t('gate:districtsWithCameras', { count: districts.filter((d) => d.district).length, total: DISTRICT_COUNT })} · {t('gate:districtEstimated')}</span>
            </div>
            <div className="gb-board-grid gb-board-head" style={{ ['--cols' as string]: DISTRICT_COLUMNS }} aria-hidden="true">
              <div>{t('gate:colProblem')}</div><div>{t('gate:colDistrict')}</div><div className="gb-num">{t('gate:colCams')}</div><div className="gb-num">{t('cameraStatus.live')}</div><div className="gb-num">{t('cameraStatus.down')}</div><div className="gb-num">{t('cameraStatus.unknown')}</div><div>{t('gate:colMix')}</div><div />
            </div>
            <DistrictBoard rows={districts} columns={DISTRICT_COLUMNS} openDistrict={openDistrict} expandAll={Boolean(query.trim()) || status !== 'all' || department !== 'all'} onToggle={setOpenDistrict} renderDrill={(row) => (
              <div className="gb-drill" role="list" aria-label={row.district ?? t('gate:noDistrict')}>
                {row.cameras.map((camera) => (
                  <div role="listitem" key={camera.camera_id} className="gb-board-grid gb-board-row gb-child" style={{ ['--cols' as string]: CAMERA_COLUMNS }}>
                    <div><StatusWord status={camera.status} /></div>
                    <div className="gb-c-cam"><button type="button" className="gb-row-link gb-nm" onClick={() => setSelected(camera)}>{cameraLabel(camera)}</button><span className="gb-id">{camera.camera_id}</span></div>
                    <div className="gb-data gb-muted">{camera.location ? `${camera.location.lat.toFixed(4)}, ${camera.location.lon.toFixed(4)}` : t('monitoring:locationMissing')}</div>
                    <div className="gb-data gb-num">{fpsLabel(camera)}</div>
                  </div>
                ))}
              </div>
            )} />
          </>}
        </div>
      ) : view === 'insights' ? (
        <CoverageLifecyclePanel department={department === 'all' ? undefined : department} />
      ) : view === 'map' ? (
        <div className="registry-map-layout">
          <section className="registry-map-list" aria-label={t('monitoring:mapList')}>
            <h3>{t('monitoring:mapList')}</h3>
            {(filteredCameras ?? []).map((camera) => <button key={camera.camera_id} aria-label={cameraLabel(camera)} onClick={() => setSelected(camera)}><CameraIcon size={17} /><span><strong>{cameraLabel(camera)}</strong><small>{camera.location ? `${camera.location.lat.toFixed(4)}, ${camera.location.lon.toFixed(4)}` : t('monitoring:locationMissing')}</small></span><SeverityBadge severity={statusToSeverity(camera.status)} label={t(`cameraStatus.${camera.status}`)} /></button>)}
            {cameras && filteredCameras?.length === 0 && <p className="monitoring-help">{t(cameras.length === 0 ? 'workspace.noCameras' : 'workspace.noMatchingCameras')}</p>}
          </section>
          <div className="registry-map-canvas">
            <MapView markers={markers} coverageGaps={coverageGaps} className="absolute inset-0" />
            <label className="registry-gap-toggle">
              <input type="checkbox" checked={showGaps} onChange={(e) => setShowGaps(e.target.checked)} />
              {tr('showGaps')}
              {showGaps && gapReport && gapReport.total_cells > 0 && <span> · {tr('coverageUncovered', { count: gapReport.uncovered_cells })}</span>}
            </label>
            {Boolean(filteredCameras?.some((camera) => !camera.location)) && <p className="registry-map-notice">{t('monitoring:noLocation', { count: filteredCameras?.filter((camera) => !camera.location).length })}</p>}
          </div>
        </div>
      ) : (
        <div className="registry-table-content">
          {loading && !cameras && <p className="text-sm text-text-tertiary">{t('cameras.loading')}</p>}
          {cameras?.length === 0 && (
            <div className="empty-state"><CameraIcon size={32} /><h3>{t('monitoring:noCameras')}</h3><p>{t('monitoring:noCamerasHelp')}</p>{isAdmin && <Button onClick={() => openOnboarding('location')}><Plus size={16} />{t('cameras.addCamera')}</Button>}</div>
          )}
          {cameras && cameras.length > 0 && filteredCameras?.length === 0 && <div className="empty-state"><p>{t('workspace.noMatchingCameras')}</p></div>}
          {filteredCameras && filteredCameras.length > 0 && (
            <Card className="registry-table-scroll overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-border-subtle text-xs uppercase tracking-wide text-text-tertiary">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.name')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.department')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.tier')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.status')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.fps')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.reconnects')}</th>
                    <th className="px-4 py-2.5 font-medium">{t('cameras.columns.tamper')}</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredCameras.map((camera) => (
                    <tr
                      key={camera.camera_id}
                      onClick={() => setSelected(camera)}
                      className="cursor-pointer border-b border-border-subtle/60 last:border-0 hover:bg-bg-overlay"
                    >
                      <td className="px-4 py-2.5">
                        <button type="button" onClick={() => setSelected(camera)} className="min-h-10 text-left font-medium text-text-primary hover:text-accent">{cameraLabel(camera)}</button>
                        <div className="text-xs text-text-tertiary">{camera.camera_id}</div>
                      </td>
                      <td className="px-4 py-2.5 text-text-secondary">{camera.department_name ?? t('common.unknown')}</td>
                      <td className="px-4 py-2.5 text-text-secondary">{camera.tier}</td>
                      <td className="px-4 py-2.5">
                        <SeverityBadge severity={statusToSeverity(camera.status)} label={t(`cameraStatus.${camera.status}`)} />
                      </td>
                      <td className="px-4 py-2.5 plate-mono text-text-secondary">
                        {fpsLabel(camera)}
                        {camera.analysed_fps != null && hasCurrentFrameRate(camera) && (
                          <div className="text-xs text-text-tertiary">
                            {tr('analysedRate', { fps: camera.analysed_fps.toFixed(1) })}
                            {camera.analysis_lag_s != null && camera.analysis_lag_s >= LAG_WARNING_S && (
                              <span className="text-sev-high"> · {tr('lagBehind', { seconds: Math.round(camera.analysis_lag_s) })}</span>
                            )}
                            {camera.people_in_view != null && (
                              <div>{tr('inView', { people: camera.people_in_view, vehicles: camera.vehicles_in_view ?? 0 })}</div>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-text-secondary">{camera.reconnects}</td>
                      <td className="px-4 py-2.5">
                        {camera.tamper_status ? (
                          <SeverityBadge
                            severity={tamperToSeverity(camera.tamper_status)}
                            label={t(`tamperStatus.${camera.tamper_status}`)}
                          />
                        ) : (
                          <span className="text-xs text-text-tertiary">{t('cameras.notMonitored')}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      )}
      </section>
      {isAdmin ? (
        <div className="registry-onboarding">
          <div><h3>{t('cameras.addCamera')}</h3><p>{t('monitoring:addHelp')}</p></div>
          <Button variant="secondary" onClick={() => openOnboarding('bulk-import')}><FileUp size={16} />{t('monitoring:importCameras')}</Button>
          <Button variant="secondary" onClick={() => openOnboarding('discover')}><Server size={16} />{t('monitoring:discoverCameras')}</Button>
        </div>
      ) : (
        <p className="monitoring-help px-1">{tr('adminToOnboard')}</p>
      )}
      </div>
      <CameraDetailModal camera={selected} onClose={() => setSelected(null)} />
      <OnboardingWizard key={onboardingPath} initialStep={onboardingPath} open={wizardOpen} onClose={() => setWizardOpen(false)} onOnboarded={refetch} />
    </div>
  )
}
