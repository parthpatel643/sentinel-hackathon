import { AlertOctagon, AlertTriangle, CheckCircle2, CircleDot, Info } from 'lucide-react'
import { cn } from '../../lib/cn'

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'ok'

const SEVERITY_META: Record<Severity, { label: string; icon: typeof Info; className: string }> = {
  critical: { label: 'Critical', icon: AlertOctagon, className: 'text-sev-critical bg-sev-critical/12' },
  high: { label: 'High', icon: AlertTriangle, className: 'text-sev-high bg-sev-high/12' },
  medium: { label: 'Medium', icon: Info, className: 'text-sev-medium bg-sev-medium/12' },
  low: { label: 'Low', icon: CircleDot, className: 'text-sev-low bg-sev-low/12' },
  ok: { label: 'Healthy', icon: CheckCircle2, className: 'text-ok bg-ok/12' },
}

interface SeverityBadgeProps {
  severity: Severity
  label?: string
  className?: string
}

/** Severity is never colour alone — every instance carries an icon and a
 * plain-language label (docs/03-UX-DESIGN.md section 2.1). */
export function SeverityBadge({ severity, label, className }: SeverityBadgeProps) {
  const meta = SEVERITY_META[severity]
  const Icon = meta.icon
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
        meta.className,
        className,
      )}
    >
      <Icon size={13} strokeWidth={2.25} />
      {label ?? meta.label}
    </span>
  )
}

const STATUS_TO_SEVERITY: Record<string, Severity> = {
  live: 'ok',
  connecting: 'medium',
  degraded: 'high',
  down: 'critical',
  unknown: 'low',
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
}

/** M13: `tamper_status` is `null` for any camera whose driver hasn't
 * wired tamper detection at all (not every driver reports it yet) —
 * distinguished from "ok" (detection is running and found nothing). */
export function tamperToSeverity(tamperStatus: string): Severity {
  return TAMPER_TO_SEVERITY[tamperStatus] ?? 'medium'
}
