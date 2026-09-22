import { CheckCircle2, Layers, ShieldCheck, XCircle } from 'lucide-react'
import { TopBar } from '../components/layout/TopBar'
import { Card } from '../components/ui/Card'
import { complianceApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import type { IntegratorCompliance } from '../lib/types'

interface ChecklistItem {
  label: string
  detail: string
  pass: boolean
}

function checklist(c: IntegratorCompliance): ChecklistItem[] {
  return [
    {
      label: 'RTSP forced to TCP transport',
      detail: 'Avoids UDP packet loss corrupting frames on congested networks.',
      pass: c.rtsp_transport_tcp_forced,
    },
    {
      label: 'PTS-driven timing',
      detail: 'Every timestamp is derived from the stream\u2019s presentation clock, not wall-clock arrival time.',
      pass: c.timing_source === 'pts',
    },
    {
      label: 'Reconnect backoff active',
      detail: `Exponential backoff from ${c.backoff.initial_s}s up to ${c.backoff.max_s}s on dropped streams.`,
      pass: c.backoff.initial_s > 0 && c.backoff.max_s >= c.backoff.initial_s,
    },
    {
      label: 'Catalogue-driven discovery',
      detail: 'Cameras are onboarded from the department catalogue, not hand-typed one at a time.',
      pass: c.catalogue_driven_discovery,
    },
    {
      label: 'Mixed-codec handling',
      detail:
        c.codecs_in_use.length > 0
          ? `Currently serving: ${c.codecs_in_use.join(', ')}.`
          : 'No live cameras to observe yet.',
      pass: c.mixed_codec_handling,
    },
    {
      label: 'Publishing to the gateway disabled',
      detail: 'This deployment only pulls streams — it never pushes into the organisers\u2019 relay.',
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
  const { data: compliance, loading, error } = usePolling(() => complianceApi.integrator(), 15000)
  const items = compliance ? checklist(compliance) : []
  const passCount = items.filter((i) => i.pass).length

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar title="Health" subtitle="System & integration status" />
      <div className="flex-1 overflow-y-auto p-6">
        <Card className="max-w-2xl overflow-hidden">
          <div className="flex items-center gap-3 border-b border-border-subtle px-5 py-4">
            <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent">
              <ShieldCheck size={18} strokeWidth={2.25} />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-text-primary">Integrator Compliance</h2>
              <p className="text-xs text-text-tertiary">
                Live status against the organisers&rsquo; pre-submission checklist
              </p>
            </div>
            {compliance && (
              <span className="ml-auto flex items-center gap-1.5 text-sm font-medium text-text-secondary">
                <Layers size={15} className="text-text-tertiary" />
                {passCount}/{items.length}
              </span>
            )}
          </div>

          {loading && !compliance && <p className="px-5 py-6 text-sm text-text-tertiary">Loading…</p>}
          {Boolean(error) && !compliance && (
            <p className="px-5 py-6 text-sm text-sev-critical">
              Could not reach the compliance endpoint. It updates every few seconds — this will clear on its own.
            </p>
          )}
          {items.map((item) => (
            <ChecklistRow key={item.label} item={item} />
          ))}
        </Card>
      </div>
    </div>
  )
}
