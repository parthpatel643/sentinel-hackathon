import { useState } from 'react'
import { Download } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { coverageApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import type { LifecycleFinding } from '../lib/types'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { RequestError } from './ui/RequestError'
import { SeverityBadge, type Severity } from './ui/SeverityBadge'

const FINDING_SEVERITY: Record<LifecycleFinding, Severity> = {
  offline: 'critical',
  amc_expired: 'high',
  maintenance: 'high',
  ageing: 'medium',
  amc_expiring: 'low',
  consent_lapsed: 'high',
  consent_expiring: 'low',
}

const FINDING_LABEL: Record<LifecycleFinding, string> = {
  ageing: 'ageing',
  amc_expired: 'amcExpired',
  amc_expiring: 'amcExpiring',
  maintenance: 'maintenance',
  offline: 'offline',
  consent_lapsed: 'consentLapsed',
  consent_expiring: 'consentExpiring',
}

/** Model 1's gap analysis in one place: the spatial half (grid cells no
 * camera covers) and the infrastructure half (ageing, AMC, maintenance). */
export function CoverageLifecyclePanel({ department }: { department?: string }) {
  const { t } = useTranslation('readiness')
  const coverage = usePolling(() => coverageApi.gaps(), 60000)
  const lifecycle = usePolling(() => coverageApi.lifecycle(department), 60000, [department])
  const [downloading, setDownloading] = useState(false)

  async function downloadCsv() {
    setDownloading(true)
    try {
      const { blob, filename } = await coverageApi.lifecycleCsv(department)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename === 'download' ? 'camera-lifecycle.csv' : filename
      link.click()
      URL.revokeObjectURL(url)
    } finally {
      setDownloading(false)
    }
  }

  const gaps = coverage.data
  const report = lifecycle.data
  const tiles: { key: LifecycleFinding; value: number }[] = report
    ? [
        { key: 'offline', value: report.offline },
        { key: 'amc_expired', value: report.amc_expired },
        { key: 'maintenance', value: report.maintenance },
        { key: 'ageing', value: report.ageing },
        { key: 'amc_expiring', value: report.amc_expiring },
        // Private (society, mall, shop) cameras are optional; their consent
        // tiles appear only once one is onboarded.
        ...(report.private_cameras
          ? [
              { key: 'consent_lapsed' as const, value: report.consent_lapsed ?? 0 },
              { key: 'consent_expiring' as const, value: report.consent_expiring ?? 0 },
            ]
          : []),
      ]
    : []

  return (
    <div className="flex flex-col gap-4 p-4">
      <p className="monitoring-help">{t('insightsHelp')}</p>

      <Card className="p-4">
        <h3 className="mb-1 text-sm font-semibold text-text-primary">{t('coverageTitle')}</h3>
        {Boolean(coverage.error) && <RequestError onRetry={coverage.refetch} />}
        {gaps && gaps.total_cells === 0 && <p className="text-sm text-text-secondary">{t('coverageEmpty')}</p>}
        {gaps && gaps.total_cells > 0 && (
          <>
            <p className="text-sm text-text-secondary">
              {t('coverageSummary', { covered: gaps.covered_cells, total: gaps.total_cells, radius: gaps.coverage_radius_m })}
              {' · '}
              <strong className="text-text-primary">{t('coverageUncovered', { count: gaps.uncovered_cells })}</strong>
            </p>
            <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-bg-inset" aria-hidden="true">
              <div className="h-full bg-ok" style={{ width: `${(gaps.covered_cells / gaps.total_cells) * 100}%` }} />
            </div>
            <p className="mt-2 text-xs text-text-tertiary">{t('coverageEstimate')}</p>
          </>
        )}
      </Card>

      <Card className="p-4">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-text-primary">{t('lifecycleTitle')}</h3>
            {report && (
              <p className="text-xs text-text-tertiary">
                {t('asOf', { date: report.as_of, years: report.ageing_threshold_years, days: report.amc_warning_days })}
              </p>
            )}
          </div>
          <Button size="sm" variant="secondary" onClick={downloadCsv} disabled={!report || downloading}>
            <Download size={15} />{t('downloadCsv')}
          </Button>
        </div>
        {Boolean(lifecycle.error) && <RequestError onRetry={lifecycle.refetch} />}
        {report && (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {tiles.map((tile) => (
                <div key={tile.key} className="rounded-md border border-border-subtle p-3">
                  <div className="text-xs text-text-tertiary">{t(FINDING_LABEL[tile.key])}</div>
                  <div className="text-xl font-semibold text-text-primary">{tile.value}</div>
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-text-tertiary">
              {t('installKnown', { known: report.install_date_known, total: report.total_cameras })}
              {report.install_date_known === 0 && ` ${t('lifecycleHint')}`}
            </p>

            <h4 className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-text-tertiary">{t('byDepartment')}</h4>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="text-xs text-text-tertiary">
                  <tr>
                    <th className="py-1.5 pr-3 font-medium">{t('department')}</th>
                    <th className="py-1.5 pr-3 font-medium">{t('total')}</th>
                    {tiles.map((tile) => <th key={tile.key} className="py-1.5 pr-3 font-medium">{t(FINDING_LABEL[tile.key])}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {report.by_department.map((row) => (
                    <tr key={row.department_name} className="border-t border-border-subtle/60">
                      <td className="py-1.5 pr-3 text-text-primary">{row.department_name}</td>
                      <td className="py-1.5 pr-3 text-text-secondary">{row.total}</td>
                      {tiles.map((tile) => <td key={tile.key} className="py-1.5 pr-3 text-text-secondary">{row[tile.key] ?? 0}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h4 className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-text-tertiary">{t('needsAttention')}</h4>
            {report.cameras_needing_attention.length === 0 ? (
              <p className="text-sm text-text-secondary">{t('noneNeedAttention')}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="text-xs text-text-tertiary">
                    <tr>
                      <th className="py-1.5 pr-3 font-medium">{t('department')}</th>
                      <th className="py-1.5 pr-3 font-medium">{t('installed')}</th>
                      <th className="py-1.5 pr-3 font-medium">{t('amcUntil')}</th>
                      <th className="py-1.5 pr-3 font-medium">{t('findings')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.cameras_needing_attention.map((camera) => (
                      <tr key={camera.camera_id} className="border-t border-border-subtle/60 align-top">
                        <td className="py-1.5 pr-3">
                          <div className="font-medium text-text-primary">{camera.name}</div>
                          <div className="text-xs text-text-tertiary">{camera.camera_id} · {camera.department_name ?? '—'}</div>
                        </td>
                        <td className="py-1.5 pr-3 text-text-secondary">
                          {camera.installed_on ?? '—'}
                          {camera.age_years != null && <div className="text-xs text-text-tertiary">{t('years', { value: camera.age_years })}</div>}
                        </td>
                        <td className="py-1.5 pr-3 text-text-secondary">{camera.amc_expires_on ?? '—'}</td>
                        <td className="py-1.5 pr-3">
                          <div className="flex flex-wrap gap-1">
                            {camera.findings.map((finding) => (
                              <SeverityBadge key={finding} severity={FINDING_SEVERITY[finding]} label={t(FINDING_LABEL[finding])} />
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  )
}
