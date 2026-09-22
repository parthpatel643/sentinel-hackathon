import { useEffect, useState } from 'react'
import { Film } from 'lucide-react'
import { alertsApi } from '../lib/api'
import { usePolling } from '../lib/usePolling'
import { TopBar } from '../components/layout/TopBar'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { SeverityBadge, type Severity } from '../components/ui/SeverityBadge'
import { SealedClipModal } from '../components/SealedClipModal'
import type { Alert, AlertStatus, EvidenceClip } from '../lib/types'

const FILTERS: { label: string; status?: AlertStatus }[] = [
  { label: 'Unacknowledged', status: 'new' },
  { label: 'Acknowledged', status: 'acknowledged' },
  { label: 'Resolved', status: 'resolved' },
  { label: 'All', status: undefined },
]

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function severityForAlert(alert: Alert): Severity {
  // priority isn't on Alert directly — priority_score already folds it in,
  // so a simple threshold stands in for it here; see watchlist/service.py.
  if (alert.priority_score >= 0.75) return 'critical'
  if (alert.priority_score >= 0.5) return 'high'
  if (alert.priority_score >= 0.25) return 'medium'
  return 'low'
}

function ClipAction({ alert, onView }: { alert: Alert; onView: (clip: EvidenceClip) => void }) {
  const [clip, setClip] = useState<EvidenceClip | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    alertsApi
      .getClip(alert.id)
      .then((c) => !cancelled && setClip(c))
      // A 404 just means no clip has been requested yet, which is already
      // this component's initial state — nothing to do either way, so any
      // other fetch error just leaves the "Seal clip" action available for
      // the operator to retry rather than getting stuck.
      .catch(() => {})
      .finally(() => !cancelled && setLoaded(true))
    return () => {
      cancelled = true
    }
  }, [alert.id])

  // While a seal is in flight, poll until it resolves — sealing runs a real
  // ~10s recording window in the background (evidence/service.py), so this
  // can't just be a one-shot fetch.
  useEffect(() => {
    if (clip?.status !== 'pending') return
    const id = setInterval(() => {
      alertsApi.getClip(alert.id).then(setClip).catch(() => {})
    }, 2000)
    return () => clearInterval(id)
  }, [alert.id, clip?.status])

  async function requestSeal() {
    setClip(await alertsApi.sealClip(alert.id))
  }

  if (!loaded) return null

  if (!clip || clip.status === 'failed') {
    return (
      <div className="flex flex-col items-end gap-1">
        <Button size="sm" variant="ghost" onClick={requestSeal}>
          <Film size={14} />
          Seal clip
        </Button>
        {clip?.status === 'failed' && <p className="text-[11px] text-sev-critical">Sealing failed — try again</p>}
      </div>
    )
  }

  if (clip.status === 'pending') {
    return (
      <Button size="sm" variant="ghost" disabled>
        <Film size={14} />
        Sealing clip…
      </Button>
    )
  }

  return (
    <Button size="sm" variant="ghost" onClick={() => onView(clip)}>
      <Film size={14} />
      Watch sealed clip
    </Button>
  )
}

function AlertRow({
  alert,
  onUpdated,
  onViewClip,
}: {
  alert: Alert
  onUpdated: () => void
  onViewClip: (clip: EvidenceClip) => void
}) {
  const [busy, setBusy] = useState<AlertStatus | null>(null)

  async function act(status: AlertStatus) {
    setBusy(status)
    try {
      await alertsApi.update(alert.id, { status })
      onUpdated()
    } finally {
      setBusy(null)
    }
  }

  const isOpen = alert.status === 'new' || alert.status === 'acknowledged' || alert.status === 'assigned'

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <SeverityBadge severity={severityForAlert(alert)} />
            <span className="text-xs text-text-tertiary">{formatTime(alert.last_seen_at)}</span>
          </div>
          <p className="plate-mono text-lg font-semibold text-text-primary">{alert.plate_text}</p>
          <p className="mt-1 text-sm text-text-secondary">
            {alert.match_rung === 'exact' ? 'Exact match' : 'Probable match (OCR ambiguity)'} on
            watchlist · {alert.camera_id}
            {alert.sighting_count > 1 && ` · ${alert.sighting_count} sightings`}
          </p>
        </div>
        {isOpen && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" disabled={busy !== null} onClick={() => act('acknowledged')}>
              {busy === 'acknowledged' ? 'Acknowledging…' : 'Acknowledge'}
            </Button>
            <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => act('false_positive')}>
              Not this vehicle
            </Button>
            <Button size="sm" disabled={busy !== null} onClick={() => act('resolved')}>
              {busy === 'resolved' ? 'Resolving…' : 'Resolve'}
            </Button>
          </div>
        )}
        {!isOpen && (
          <SeverityBadge
            severity={alert.status === 'false_positive' ? 'low' : 'ok'}
            label={alert.status === 'false_positive' ? 'Not this vehicle' : 'Resolved'}
          />
        )}
      </div>
      <div className="mt-3 flex justify-end border-t border-border-subtle/60 pt-3">
        <ClipAction alert={alert} onView={onViewClip} />
      </div>
    </Card>
  )
}

export function Alerts() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>(FILTERS[0])
  const [viewingClip, setViewingClip] = useState<EvidenceClip | null>(null)
  const { data: alerts, refetch } = usePolling(() => alertsApi.list(filter.status), 6000, [filter.status])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar title="Alerts" subtitle={alerts ? `${alerts.length} shown` : undefined} />
      <div className="flex gap-2 border-b border-border-subtle px-6 py-3">
        {FILTERS.map((f) => (
          <Button
            key={f.label}
            size="sm"
            variant={filter.label === f.label ? 'primary' : 'secondary'}
            onClick={() => setFilter(f)}
          >
            {f.label}
          </Button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {!alerts && <p className="text-sm text-text-tertiary">Loading…</p>}
        {alerts?.length === 0 && <p className="text-sm text-text-tertiary">No alerts here.</p>}
        <div className="flex flex-col gap-3">
          {alerts?.map((alert) => (
            <AlertRow key={alert.id} alert={alert} onUpdated={refetch} onViewClip={setViewingClip} />
          ))}
        </div>
      </div>
      <SealedClipModal clip={viewingClip} onClose={() => setViewingClip(null)} />
    </div>
  )
}
