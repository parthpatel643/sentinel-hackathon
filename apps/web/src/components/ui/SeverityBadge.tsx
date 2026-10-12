import { AlertOctagon, AlertTriangle, CheckCircle2, CircleDot, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '../../lib/cn'

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'ok'

const SEVERITY_META: Record<Severity, { labelKey: string; icon: typeof Info; className: string }> = {
  critical: { labelKey: 'severity.critical', icon: AlertOctagon, className: 'text-sev-critical' },
  high: { labelKey: 'severity.high', icon: AlertTriangle, className: 'text-sev-high' },
  medium: { labelKey: 'severity.medium', icon: Info, className: 'text-sev-medium' },
  low: { labelKey: 'severity.low', icon: CircleDot, className: 'text-text-secondary' },
  ok: { labelKey: 'severity.ok', icon: CheckCircle2, className: 'text-ok' },
}

interface SeverityBadgeProps {
  severity: Severity
  label?: string
  className?: string
}

/** Severity is never colour alone — every instance carries an icon and a
 * plain-language label (docs/03-UX-DESIGN.md section 2.1). */
export function SeverityBadge({ severity, label, className }: SeverityBadgeProps) {
  const { t } = useTranslation()
  const meta = SEVERITY_META[severity]
  const Icon = meta.icon
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap py-1 text-[13px] font-bold',
        meta.className,
        className,
      )}
    >
      <Icon size={14} strokeWidth={2.4} aria-hidden="true" />
      {label ?? t(meta.labelKey)}
    </span>
  )
}

const STATUS_TO_SEVERITY: Record<string, Severity> = {
  live: 'ok',
  connecting: 'medium',
  degraded: 'high',
  down: 'critical',
  unknown: 'low',
  stale: 'high',
}

export function statusToSeverity(status: string): Severity {
  return STATUS_TO_SEVERITY[status] ?? 'low'
}

const PRIORITY_TO_SEVERITY: Record<string, Severity> = {
  critical: 'critical',
  high: 'high',
  medium: 'medium',
  low: 'low',
}

export function priorityToSeverity(priority: string): Severity {
  return PRIORITY_TO_SEVERITY[priority] ?? 'medium'
}

const TAMPER_TO_SEVERITY: Record<string, Severity> = {
  ok: 'ok',
  covered: 'critical',
  blurred: 'high',
  moved: 'high',
  view_lost: 'high',
}

/** M13: `tamper_status` is `null` for any camera whose driver hasn't
 * wired tamper detection at all (not every driver reports it yet) —
 * distinguished from "ok" (detection is running and found nothing). */
export function tamperToSeverity(tamperStatus: string): Severity {
  return TAMPER_TO_SEVERITY[tamperStatus] ?? 'medium'
}
