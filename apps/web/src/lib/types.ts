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

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface StreamProfile {
  protocol: string
  url: string
}

export type CameraStatus = 'unknown' | 'connecting' | 'live' | 'degraded' | 'down'
export type CameraTier = 'a_continuous' | 'b_sampled' | 'c_event' | string

export interface Camera {
  camera_id: string
  name: string
  driver_id: string
  department_name: string | null
  site_name: string | null
  location: GeoPoint | null
  tier: CameraTier
  status: CameraStatus
  last_seen_at: string | null
  measured_fps: number | null
  declared_fps: number | null
  reconnects: number
  discontinuities: number
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
  observed_at: string
  snapshot_uri: string | null
  node_id: string
}

export type MatchRung = 'exact' | 'ambiguity_class'

export interface RoutePoint {
  camera_id: string
  camera_name: string
  location: GeoPoint | null
  observed_at: string
  plate_text: string
  plate_confidence: number
  match_rung: MatchRung
  snapshot_uri: string | null
  confirmed: boolean
}

export interface VehicleRoute {
  plate_normalised: string
  total_sightings: number
  first_seen_at: string | null
  last_seen_at: string | null
  points: RoutePoint[]
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
  first_seen_at: string
  last_seen_at: string
  resolved_by: string | null
  resolution_note: string | null
  created_at: string
}

export interface BoloResult {
  watchlist_entry: WatchlistEntry
  retro_alerts_created: number
  retro_sightings_found: number
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
