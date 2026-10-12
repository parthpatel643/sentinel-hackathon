import { useTranslation } from 'react-i18next'
import { cn } from '../../lib/cn'

const STATUS_CLASS: Record<string, string> = {
  live: 'gb-live',
  down: 'gb-down',
  unknown: 'gb-unknown',
  degraded: 'gb-degraded',
  stale: 'gb-stale',
  connecting: 'gb-idle',
}

/** Camera status as glyph + word. Colour is never the only signal, and
 * Unknown is hatched grey, never green. */
export function StatusWord({ status, className }: { status: string; className?: string }) {
  const { t } = useTranslation()
  return <span className={cn('gb-status', STATUS_CLASS[status] ?? 'gb-unknown', className)}>{t(`cameraStatus.${status}`, { defaultValue: status })}</span>
}
