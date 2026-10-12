import { Fragment, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '../../lib/cn'
import type { DistrictRollup } from '../../lib/districts'

/** A district's camera mix as one bar: down, degraded, live, unknown. */
export function MixBar({ row }: { row: DistrictRollup }) {
  const total = row.cameras.length || 1
  const parts = [
    { key: 'down', n: row.down },
    { key: 'degraded', n: row.degraded },
    { key: 'stale', n: row.stale },
    { key: 'live', n: row.live },
    { key: 'unknown', n: row.unknown + row.other },
  ].filter((p) => p.n > 0)
  return <span className="gb-comp" aria-hidden="true">{parts.map((p) => <i key={p.key} className={`gb-${p.key}`} style={{ flex: p.n / total }} />)}</span>
}

export function WorstState({ row }: { row: DistrictRollup }) {
  const { t } = useTranslation()
  if (row.down) return <span className="gb-status gb-down">{t('gate:problemDown', { count: row.down })}</span>
  if (row.degraded) return <span className="gb-status gb-degraded">{t('gate:problemDegraded', { count: row.degraded })}</span>
  if (row.stale) return <span className="gb-status gb-stale">{t('gate:problemStale', { count: row.stale })}</span>
  if (row.unknown) return <span className="gb-status gb-unknown">{t('gate:problemUnknown', { count: row.unknown })}</span>
  if (row.other) return <span className="gb-status gb-idle">{t('gate:problemConnecting', { count: row.other })}</span>
  return <span className="gb-status gb-live">{t('gate:allLive')}</span>
}

interface DistrictBoardProps {
  rows: DistrictRollup[]
  columns: string
  compact?: boolean
  openDistrict?: string | null
  /** Filters are active: every district opens so matches are visible. */
  expandAll?: boolean
  onToggle?: (district: string | null) => void
  renderDrill?: (row: DistrictRollup) => ReactNode
}

const ID_PREVIEW = 4

export const districtKey = (district: string | null) => district ?? '__none__'

export function DistrictBoard({ rows, columns, compact = false, openDistrict, expandAll = false, onToggle, renderDrill }: DistrictBoardProps) {
  const { t } = useTranslation()
  return (
    <div role={onToggle ? undefined : 'list'}>
      {rows.map((row) => {
        const name = row.district ?? t('gate:noDistrict')
        const open = expandAll || (openDistrict !== undefined && openDistrict === districtKey(row.district))
        const cells = (
          <>
            {!compact && <div><WorstState row={row} /></div>}
            <div className="gb-c-cam"><span className="gb-nm">{name}</span>{!row.district && <span className="gb-id" title={row.cameras.map((c) => c.camera_id).join(' ')}>{row.cameras.slice(0, ID_PREVIEW).map((c) => c.camera_id).join(' ')}{row.cameras.length > ID_PREVIEW && ` ${t('gate:moreIds', { count: row.cameras.length - ID_PREVIEW })}`}</span>}</div>
            <div className="gb-c-num">{row.cameras.length}</div>
            {!compact && <div className="gb-c-num">{row.live}</div>}
            {!compact && <div className="gb-c-num">{row.down}</div>}
            {!compact && <div className="gb-c-num">{row.unknown}</div>}
            <div><MixBar row={row} /></div>
            {compact && <div><WorstState row={row} /></div>}
            {onToggle && <div className="gb-c-act">{open ? <ChevronDown className="gb-ico" aria-hidden="true" /> : <ChevronRight className="gb-ico" aria-hidden="true" />}</div>}
          </>
        )
        return (
          <Fragment key={districtKey(row.district)}>
            {onToggle
              ? <button type="button" aria-expanded={open} aria-label={`${name} · ${t('gate:cameras', { count: row.cameras.length })}`}
                  className={cn('gb-board-grid gb-board-row gb-row-button', open && 'gb-open')} style={{ ['--cols' as string]: columns }}
                  onClick={() => onToggle(open ? null : districtKey(row.district))}>{cells}</button>
              : <div role="listitem" className="gb-board-grid gb-board-row" style={{ ['--cols' as string]: columns }}>{cells}</div>}
            {open && renderDrill?.(row)}
          </Fragment>
        )
      })}
    </div>
  )
}
