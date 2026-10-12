/** Wire types — mirror the Pydantic response models in
 * services/core_api/src/core_api/{registry,detections,watchlist}/schemas.py
 * field-for-field. Kept as one file so a backend schema change is easy to
 * diff against. */

export interface GeoPoint {
  lat: number
  lon: number
}

export interface AuthUser {
  id: string
  email: string
  full_name: string
  role: string
  active: boolean
  created_at: string
}

export interface UserCreate {
  email: string
  password: string
  full_name: string
  role?: string
}

export interface RetentionPreview {
  detections_older_than_days: number
  clips_older_than_days: number
  detections_affected: number
  clips_affected: number
  clips_bytes_affected: number
}

export interface RetentionExecutionResult {
  detections_older_than_days: number
  clips_older_than_days: number
  detections_deleted: number
  clips_deleted: number
  clips_bytes_deleted: number
}

export interface AuditLogEntry {
  id: string
  seq: number
  actor_email: string | null
  action: string
  resource_type: string
  resource_id: string | null
  detail: Record<string, unknown>
  created_at: string
  prev_hash: string
  row_hash: string
}

export interface AuditChainVerification {
  intact: boolean
  rows_checked: number
  first_broken_seq: number | null
  detail: string | null
}

export interface Zone {
  id: string
  camera_id: string
  name: string
  rule_type: string
  polygon: number[][]
  dwell_threshold_s: number
  expected_direction_deg: number
  direction_tolerance_deg: number
  stopped_speed_threshold: number
  active: boolean
  created_at: string
}

export interface ZoneCreate {
  name: string
  rule_type: string
  polygon: number[][]
  dwell_threshold_s?: number
  expected_direction_deg?: number
  direction_tolerance_deg?: number
  stopped_speed_threshold?: number
}

export interface ZoneEvent {
  id: string
  zone_id: string
  zone_name: string | null
  camera_id: string
  rule_type: string
  track_id: string
  object_class?: 'vehicle' | 'person'
  dwell_time_s: number | null
  heading_deg: number | null
  /** Processing time — ordering only, never display it. */
  observed_at: string
  /** The camera's burned-in clock on the frame that fired it; null is time unknown. */
  camera_time: string | null
  status?: ZoneEventStatus
  resolved_by?: string | null
}

export type ZoneEventStatus = 'new' | 'acknowledged' | 'resolved' | 'false_positive'

/** A camera whose view changed: moved (knocked, re-aimed) or no longer
 * recognisable (turned away, obstructed, weather). */
export interface CameraEvent {
  id: string
  /** Names the before/after evidence frames. */
  event_id: string
  camera_id: string
  kind: 'view_shifted' | 'view_unrecognised'
  /** Displacement of the view, % of frame width. */
  shift_pct: number | null
  rotation_deg: number | null
  scale: number | null
  match_ratio: number | null
  has_snapshots: boolean
  /** Processing time — ordering only, never display it. */
  observed_at: string
  /** The camera's burned-in clock when the change was confirmed; null is unknown. */
  camera_time: string | null
  status: ZoneEventStatus
  resolved_by: string | null
  restored_at: string | null
  created_at: string
}

export interface IntegrationStatus {
  provider_id: string
  name: string
  description: string
  mode: string
  connected: boolean
  detail: string
  sample_operation: string
  sample_latency_ms: number | null
  checked_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface StreamProfile {
  protocol: string
  url: string
}

export type CameraStatus = 'unknown' | 'connecting' | 'live' | 'degraded' | 'down' | 'stale'
export type CameraTier = 'a_continuous' | 'b_sampled' | 'c_event' | string

export interface Camera {
  camera_id: string
  name: string
  /** Readable label derived from `name`; `name` stays the catalogue's own value. */
  display_name?: string
  /** Place or administrative area lifted out of `name`, if any. */
  locality?: string
  driver_id: string
  department_name: string | null
  site_name: string | null
  location: GeoPoint | null
  tier: CameraTier
  status: CameraStatus
  last_seen_at: string | null
  measured_fps: number | null
  /** Frames per stream-second run through ANPR, as the camera's tier schedules it. */
  analysed_fps?: number | null
  /** How far behind live the worker's analysis was at its last heartbeat. */
  analysis_lag_s?: number | null
  /** Most people / vehicles in one analysed frame at the last heartbeat. Counts, never identities. */
  people_in_view?: number | null
  vehicles_in_view?: number | null
  declared_fps: number | null
  reconnects: number
  discontinuities: number
  tamper_status: string | null
  source: string
  attributes: Record<string, string>
  profiles: StreamProfile[]
  created_at: string
  updated_at: string
}

export interface CameraStream {
  available: boolean
  hls_url: string | null
  reason: string | null
}

export interface StreamProfileIn {
  protocol: string
  url: string
  codec?: string | null
  width?: number | null
  height?: number | null
  declared_fps?: number | null
}

export interface CameraCreate {
  camera_id: string
  name: string
  driver_id?: string
  department_name?: string | null
  site_name?: string | null
  location?: GeoPoint | null
  tier?: string
  profiles?: StreamProfileIn[]
  attributes?: Record<string, string>
}

export interface BulkImportRowResult {
  row_number: number
  camera_id: string | null
  ok: boolean
  error: string | null
}

export interface BulkImportResult {
  dry_run: boolean
  total_rows: number
  succeeded: number
  failed: number
  rows: BulkImportRowResult[]
}

export interface Department {
  id: string
  name: string
  code: string | null
  camera_count: number
}

export interface Detection {
  event_id: string
  camera_id: string
  plate_text: string
  plate_normalised: string
  plate_confidence: number
  format_valid: boolean
  frames_voted: number
  vehicle_class: string | null
  vehicle_track_id: string | null
  /**
   * The clock the camera burned into the evidence frame — the only time to
   * show for a sighting. Null: the clock was unreadable, so the time is unknown.
   */
  camera_time: string | null
  /** When the edge processed the footage. Ordering only — never display it. */
  observed_at: string
  /**
   * When we recorded the detection. The camera's clock can be months behind —
   * the government feeds replay archived footage — so recency is judged by
   * this one. Never display it as the sighting's time.
   */
  ingested_at: string
  snapshot_uri: string | null
  node_id: string
}

export type MatchRung = 'exact' | 'ambiguity_class' | 'edit_distance' | 'partial_attribute'

export interface RoutePoint {
  /** Addresses the snapshot endpoint; `snapshot_uri` is an internal reference. */
  event_id?: string
  camera_id: string
  camera_name: string
  location: GeoPoint | null
  /** The clock visible in this sighting's evidence frame; null in `VehicleRoute.untimed`. */
  camera_time: string | null
  plate_text: string
  plate_confidence: number
  match_rung: MatchRung
  snapshot_uri: string | null
  confirmed: boolean
  /** Speed a vehicle would need from the previous hop to this one. */
  implied_speed_kmh?: number | null
  /** Beyond any road vehicle: a cloned plate, a wrong camera clock, or a misattributed read. */
  infeasible?: boolean
}

export interface VehicleRoute {
  plate_normalised: string
  total_sightings: number
  /** The camera's clock on the earliest timed sighting. */
  first_seen_at: string | null
  /** The camera's clock on the latest timed sighting. */
  last_seen_at: string | null
  /** Sightings with a readable camera clock, in that clock's order. */
  points: RoutePoint[]
  /** Sightings whose camera clock was unreadable: real, but off the timeline. */
  untimed: RoutePoint[]
}

export type EntryType = 'stolen_vehicle' | 'wanted_vehicle' | 'missing_person' | 'suspect' | 'bolo' | string
export type Priority = 'low' | 'medium' | 'high' | 'critical'

export interface WatchlistEntry {
  id: string
  plate_normalised: string
  entry_type: EntryType
  priority: Priority
  case_reference: string | null
  requested_by: string | null
  notes: string | null
  active: boolean
  valid_from: string
  valid_until: string | null
  created_at: string
}

export type AlertStatus =
  | 'new'
  | 'acknowledged'
  | 'assigned'
  | 'in_progress'
  | 'resolved'
  | 'false_positive'

export interface Alert {
  id: string
  watchlist_entry_id: string
  camera_id: string
  detection_event_id: string
  plate_text: string
  match_rung: MatchRung
  match_confidence: number
  priority_score: number
  status: AlertStatus
  sighting_count: number
  /** Processing time of the earliest sighting — ordering only, never display it. */
  first_seen_at: string
  /** Processing time of the latest sighting — ordering only, never display it. */
  last_seen_at: string
  /** The camera's clock on the earliest sighting; null is time unknown. */
  first_seen_camera_time: string | null
  /** The camera's clock on the latest sighting; null is time unknown. */
  last_seen_camera_time: string | null
  resolved_by: string | null
  resolution_note: string | null
  created_at: string
}

export type EvidenceClipStatus = 'pending' | 'sealed' | 'failed'

export interface EvidenceClip {
  id: string
  alert_id: string
  camera_id: string
  status: EvidenceClipStatus
  sha256: string | null
  duration_s: number | null
  error: string | null
  created_at: string
  sealed_at: string | null
}

export interface BoloResult {
  watchlist_entry: WatchlistEntry
  retro_alerts_created: number
  retro_sightings_found: number
  /** An active entry already watched this plate; it was returned, not duplicated. */
  already_armed?: boolean
}

export interface CoverageCell {
  center: GeoPoint
  covered: boolean
  nearest_camera_id: string | null
  nearest_camera_distance_m: number | null
}

export interface CoverageGapReport {
  total_cells: number
  covered_cells: number
  uncovered_cells: number
  coverage_radius_m: number
  cell_size_m: number
  cells: CoverageCell[]
}

export interface IntegratorCompliance {
  rtsp_transport_tcp_forced: boolean
  publishing_to_gateway_disabled: boolean
  timing_source: string
  catalogue_driven_discovery: boolean
  mixed_codec_handling: boolean
  codecs_in_use: string[]
  backoff: {
    initial_s: number
    max_s: number
  }
}

export interface PlateLookupMatch {
  entry_type: string
  priority: string
  match_rung: string
  case_reference: string | null
}

export interface PlateLookup {
  plate_normalised: string
  status: string
  matches: PlateLookupMatch[]
  /** The camera's clock on the latest sighting. Null with a camera name: time unknown. */
  last_seen_at: string | null
  last_seen_camera_name: string | null
}

export interface FieldSighting {
  id: string
  client_report_id: string
  reported_by: string
  plate_text: string
  lat: number | null
  lon: number | null
  notes: string | null
  has_photo: boolean
  created_at: string
}

export type LifecycleFinding =
  | 'ageing'
  | 'amc_expired'
  | 'amc_expiring'
  | 'maintenance'
  | 'offline'
  | 'consent_lapsed'
  | 'consent_expiring'

export interface LifecycleCamera {
  camera_id: string
  name: string
  department_name: string | null
  status: CameraStatus
  installed_on: string | null
  age_years: number | null
  amc_expires_on: string | null
  maintenance_status: string | null
  vendor: string | null
  model: string | null
  findings: LifecycleFinding[]
  ownership?: 'government' | 'private' | null
  consent_ref?: string | null
  consent_expires_on?: string | null
}

export interface DepartmentLifecycle {
  department_name: string
  total: number
  ageing: number
  amc_expired: number
  amc_expiring: number
  maintenance: number
  offline: number
  consent_lapsed?: number
  consent_expiring?: number
  install_date_unknown: number
}

export interface LifecycleReport {
  as_of: string
  ageing_threshold_years: number
  amc_warning_days: number
  total_cameras: number
  install_date_known: number
  amc_date_known: number
  ageing: number
  amc_expired: number
  amc_expiring: number
  maintenance: number
  offline: number
  /** Cameras onboarded with ownership=private; consent tiles show only when > 0. */
  private_cameras?: number
  consent_lapsed?: number
  consent_expiring?: number
  by_department: DepartmentLifecycle[]
  cameras_needing_attention: LifecycleCamera[]
}

export type DeviceDriver = 'onvif' | 'hikvision' | 'dahua'

export interface DeviceDiscoveryRequest {
  driver: DeviceDriver
  host: string
  username?: string
  password?: string
  department_name?: string
  site_name?: string
  dry_run: boolean
}

export interface DeviceDiscoveryResult {
  dry_run: boolean
  discovered: { camera_id: string; name: string; stream_count: number; stream_urls: string[] }[]
  onboarded: string[]
  updated: string[]
  failed: { camera_id: string; error: string }[]
}
