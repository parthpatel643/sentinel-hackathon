import { useState } from 'react'
import { CheckCircle2, RefreshCw, ShieldCheck, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { TopBar } from '../components/layout/TopBar'
import { complianceApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import type { IntegratorCompliance } from '../lib/types'
import { RequestError } from '../components/ui/RequestError'
import './management-workspace.css'

interface ChecklistItem {
  key: string
  label: string
  detail: string
  pass: boolean
}

function checklist(c: IntegratorCompliance, t: TFunction): ChecklistItem[] {
  return [
    {
      key: 'rtspTcp',
      label: t('health.checklist.rtspTcp.label'),
      detail: t('health.checklist.rtspTcp.detail'),
      pass: c.rtsp_transport_tcp_forced,
    },
    {
      key: 'ptsTiming',
      label: t('health.checklist.ptsTiming.label'),
      detail: t('health.checklist.ptsTiming.detail'),
      pass: c.timing_source === 'pts',
    },
    {
      key: 'backoff',
      label: t('health.checklist.backoff.label'),
      detail: t('health.checklist.backoff.detail', { initial: c.backoff.initial_s, max: c.backoff.max_s }),
      pass: c.backoff.initial_s > 0 && c.backoff.max_s >= c.backoff.initial_s,
    },
    {
      key: 'catalogue',
      label: t('health.checklist.catalogue.label'),
      detail: t('health.checklist.catalogue.detail'),
      pass: c.catalogue_driven_discovery,
    },
    {
      key: 'codecs',
      label: t('health.checklist.codecs.label'),
      detail:
        c.codecs_in_use.length > 0
          ? t('health.checklist.codecs.detailWithCodecs', { codecs: c.codecs_in_use.join(', ') })
          : t('health.checklist.codecs.detailEmpty'),
      pass: c.mixed_codec_handling,
    },
    {
      key: 'publishing',
      label: t('health.checklist.publishing.label'),
      detail: t('health.checklist.publishing.detail'),
      pass: c.publishing_to_gateway_disabled,
    },
  ]
}

function ChecklistRow({ item }: { item: ChecklistItem }) {
  const { t } = useTranslation()
  return (
    <div className="compliance-check" data-check-result={item.pass ? 'pass' : 'fail'}>
      {item.pass ? (
        <CheckCircle2 size={20} className="mt-0.5 flex-shrink-0 text-ok" />
      ) : (
        <XCircle size={20} className="mt-0.5 flex-shrink-0 text-sev-critical" />
      )}
      <div className="min-w-0">
        <p className="text-sm font-medium text-text-primary">{item.label}</p>
        <p className="text-xs text-text-tertiary">{item.detail}</p>
      </div>
      <span className={item.pass ? 'compliance-result is-pass' : 'compliance-result is-fail'}>{t(item.pass ? 'management:passed' : 'management:needsAttention')}</span>
    </div>
  )
}

export function Health() {
  const { t } = useTranslation()
  const { data: compliance, loading, error, refetch } = usePolling(() => complianceApi.integrator(), 15000)
  const [filter, setFilter] = useState<'all' | 'failed'>('all')
  const items = compliance && !error ? checklist(compliance, t) : []
  const passCount = items.filter((i) => i.pass).length
  const groups = [
    { title: 'transport', keys: ['rtspTcp', 'ptsTiming', 'backoff'] },
    { title: 'discovery', keys: ['catalogue', 'codecs'] },
    { title: 'publishing', keys: ['publishing'] },
  ]

  return (
    <div className="management-workspace flex min-h-0 flex-1 flex-col">
      <TopBar title={t('nav.health')} subtitle={t('health.subtitle')} />
      <div className="page-body management-body">
        <div className="management-heading">
          <div><h2>{t('management:healthTitle')}</h2><p>{t('management:healthIntro')}</p></div>
          <button className="management-action" onClick={refetch} disabled={loading}><RefreshCw size={17} aria-hidden="true" />{t('management:refreshChecks')}</button>
        </div>
        {Boolean(error) && <RequestError onRetry={refetch} />}
        <section className="compliance-summary" aria-label={t('management:healthSummary')}>
          <ShieldCheck size={30} aria-hidden="true" />
          <div>
            <h3>{t('health.integratorCompliance')}</h3>
            <p>{error ? t('management:unavailable') : !compliance ? t('health.loading') : t('management:passing', { count: passCount, total: items.length })}</p>
          </div>
          {!!items.length && <span className={passCount === items.length ? 'text-ok' : 'text-sev-critical'}>{t('management:failed', { count: items.length - passCount })}</span>}
        </section>
        <div className="compliance-workbench">
          <section className="compliance-results" aria-label={t('management:allChecks')}>
            <div className="compliance-filters">
              <button aria-pressed={filter === 'all'} onClick={() => setFilter('all')}>{t('management:allChecks')}</button>
              <button aria-pressed={filter === 'failed'} onClick={() => setFilter('failed')}>{t('management:needsAttention')}</button>
            </div>
            {!!error && <p className="management-empty">{t('management:healthUnavailable')}</p>}
            {loading && !compliance && <p role="status" className="management-empty">{t('health.loading')}</p>}
            {!error && compliance && filter === 'failed' && passCount === items.length && <p className="management-empty">{t('management:healthEmpty')}</p>}
            {groups.map((group) => {
              const checks = items.filter((item) => group.keys.includes(item.key) && (filter === 'all' || !item.pass))
              return checks.length > 0 && <section key={group.title} className="compliance-group" aria-labelledby={`compliance-${group.title}`}>
                <h3 id={`compliance-${group.title}`}>{t(`management:${group.title}`)}</h3>
                {checks.map((item) => <ChecklistRow key={item.key} item={item} />)}
              </section>
            })}
          </section>
          <aside className="compliance-context">
            <h3>{t('management:healthScope')}</h3>
            <p>{t('management:healthScopeHelp')}</p>
            <p>{t('management:polling')}</p>
          </aside>
        </div>
      </div>
    </div>
  )
}
