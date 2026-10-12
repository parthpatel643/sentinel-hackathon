import type { Alert, AlertStatus } from './types'
import type { Severity } from '../components/ui/SeverityBadge'

export function severityForAlert(alert: Pick<Alert, 'priority_score'>): Severity {
  if (alert.priority_score >= 0.75) return 'critical'
  if (alert.priority_score >= 0.5) return 'high'
  if (alert.priority_score >= 0.25) return 'medium'
  return 'low'
}

export const OPEN_STATUSES: AlertStatus[] = ['new']
export const WORKING_STATUSES: AlertStatus[] = ['acknowledged', 'assigned', 'in_progress']
export const CLOSED_STATUSES: AlertStatus[] = ['resolved', 'false_positive']

/** One watchlist vehicle on the board: every alert for the plate, folded. */
export interface VehicleGroup {
  plate: string
  alerts: Alert[]
  /** The alert the row acts on: newest by camera clock, then by processing time. */
  lead: Alert
  hits: number
  sightings: number
  cameraIds: string[]
  /** Highest priority across the group. */
  priorityScore: number
  unseen: number
  /** True when no alert in the group carries a camera-clock time. */
  timeUnknown: boolean
  /** Latest camera-clock time across the group, or null. */
  lastCameraTime: string | null
}

function newer(a: Alert, b: Alert) {
  const at = a.last_seen_camera_time ? Date.parse(a.last_seen_camera_time) : -Infinity
  const bt = b.last_seen_camera_time ? Date.parse(b.last_seen_camera_time) : -Infinity
  if (at !== bt) return at > bt ? a : b
  return Date.parse(a.last_seen_at) >= Date.parse(b.last_seen_at) ? a : b
}

/** Repeat hits on one plate are one decision for an operator, so the board
 * shows one row per vehicle. Ranked by priority, then camera time; within a
 * priority, vehicles with no readable camera clock sink below timed ones
 * (their order would be a guess). */
export function groupAlertsByVehicle(alerts: Alert[]): VehicleGroup[] {
  const byPlate = new Map<string, Alert[]>()
  for (const alert of alerts) byPlate.set(alert.plate_text, [...(byPlate.get(alert.plate_text) ?? []), alert])
  const groups: VehicleGroup[] = [...byPlate.entries()].map(([plate, list]) => {
    const lead = list.reduce(newer)
    const timed = list.filter((a) => a.last_seen_camera_time)
    return {
      plate,
      alerts: list,
      lead,
      hits: list.length,
      sightings: list.reduce((sum, a) => sum + a.sighting_count, 0),
      cameraIds: [...new Set(list.map((a) => a.camera_id))],
      priorityScore: Math.max(...list.map((a) => a.priority_score)),
      unseen: list.filter((a) => a.status === 'new').length,
      timeUnknown: timed.length === 0,
      lastCameraTime: timed.length ? timed.reduce(newer).last_seen_camera_time : null,
    }
  })
  return groups.sort((a, b) => {
    if (a.priorityScore !== b.priorityScore) return b.priorityScore - a.priorityScore
    if (a.timeUnknown !== b.timeUnknown) return a.timeUnknown ? 1 : -1
    return Date.parse(b.lastCameraTime ?? b.lead.last_seen_at) - Date.parse(a.lastCameraTime ?? a.lead.last_seen_at)
  })
}
