import { CheckCircle2, Layers, ShieldCheck, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { TopBar } from '../components/layout/TopBar'
import { Card } from '../components/ui/Card'
import { complianceApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import type { IntegratorCompliance } from '../lib/types'
import { RequestError } from '../components/ui/RequestError'

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
  return (
    <div className="flex items-start gap-3 border-b border-border-subtle/60 px-5 py-4 last:border-0">
      {item.pass ? (
        <CheckCircle2 size={20} className="mt-0.5 flex-shrink-0 text-ok" />
      ) : (
        <XCircle size={20} className="mt-0.5 flex-shrink-0 text-sev-critical" />
      )}
      <div className="min-w-0">
        <p className="text-sm font-medium text-text-primary">{item.label}</p>
        <p className="text-xs text-text-tertiary">{item.detail}</p>
      </div>
    </div>
  )
}

export function Health() {
  const { t } = useTranslation()
  const { data: compliance, loading, error, refetch } = usePolling(() => complianceApi.integrator(), 15000)
  const items = compliance ? checklist(compliance, t) : []
  const passCount = items.filter((i) => i.pass).length

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar title={t('nav.health')} subtitle={t('health.subtitle')} />
      <div className="page-body">
        {Boolean(error) && <RequestError onRetry={refetch} />}
        <Card className="max-w-4xl overflow-hidden">
          <div className="flex items-center gap-3 border-b border-border-subtle px-5 py-4">
            <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent">
              <ShieldCheck size={18} strokeWidth={2.25} />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-text-primary">{t('health.integratorCompliance')}</h2>
              <p className="text-xs text-text-tertiary">{t('health.liveStatus')}</p>
            </div>
            {compliance && (
              <span className="ml-auto flex items-center gap-1.5 text-sm font-medium text-text-secondary">
                <Layers size={15} className="text-text-tertiary" />
                {passCount}/{items.length}
              </span>
            )}
          </div>

          {loading && !compliance && <p className="px-5 py-6 text-sm text-text-tertiary">{t('health.loading')}</p>}
          {items.map((item) => (
            <ChecklistRow key={item.key} item={item} />
          ))}
        </Card>
      </div>
    </div>
  )
}
