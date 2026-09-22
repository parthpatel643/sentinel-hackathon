/** Every core_api call the frontend needs, grouped by resource. Route
 * components call these, never `lib/http` directly — this file is the one
 * place that knows the URL shapes. */

import { get, getBlob, patch, post } from './http'
import type {
  Alert,
  AlertStatus,
  AuthUser,
  BoloResult,
  Camera,
  CameraStream,
  CoverageGapReport,
  Department,
  Detection,
  EvidenceClip,
  IntegratorCompliance,
  TokenResponse,
  VehicleRoute,
  WatchlistEntry,
} from './types'

export const authApi = {
  login: (email: string, password: string) =>
    post<TokenResponse>('/api/v1/auth/login', { email, password }),
  me: () => get<AuthUser>('/api/v1/auth/me'),
}

export const camerasApi = {
  list: (departmentName?: string) =>
    get<Camera[]>(`/api/v1/cameras${departmentName ? `?department=${encodeURIComponent(departmentName)}` : ''}`),
  get: (cameraId: string) => get<Camera>(`/api/v1/cameras/${encodeURIComponent(cameraId)}`),
  stream: (cameraId: string) => get<CameraStream>(`/api/v1/cameras/${encodeURIComponent(cameraId)}/stream`),
}

export const departmentsApi = {
  list: () => get<Department[]>('/api/v1/departments'),
}

export const coverageApi = {
  gaps: () => get<CoverageGapReport>('/api/v1/coverage/gaps'),
}

export const complianceApi = {
  integrator: () => get<IntegratorCompliance>('/api/v1/compliance/integrator'),
}

export const detectionsApi = {
  search: (params: { plate?: string; cameraId?: string; limit?: number } = {}) => {
    const query = new URLSearchParams()
    if (params.plate) query.set('plate', params.plate)
    if (params.cameraId) query.set('camera_id', params.cameraId)
    if (params.limit) query.set('limit', String(params.limit))
    const qs = query.toString()
    return get<Detection[]>(`/api/v1/detections${qs ? `?${qs}` : ''}`)
  },
  vehicleRoute: (plate: string) => get<VehicleRoute>(`/api/v1/vehicles/${encodeURIComponent(plate)}/route`),
  movementReport: (plate: string) => getBlob(`/api/v1/vehicles/${encodeURIComponent(plate)}/movement-report`),
}

export const watchlistApi = {
  list: (activeOnly = true) => get<WatchlistEntry[]>(`/api/v1/watchlist?active_only=${activeOnly}`),
  bolo: (payload: {
    plate: string
    entry_type?: string
    priority?: string
    case_reference?: string
    requested_by?: string
    notes?: string
  }) => post<BoloResult>('/api/v1/bolo', payload),
}

export const alertsApi = {
  list: (status?: AlertStatus) => get<Alert[]>(`/api/v1/alerts${status ? `?status=${status}` : ''}`),
  update: (alertId: string, payload: { status: AlertStatus; resolved_by?: string; resolution_note?: string }) =>
    patch<Alert>(`/api/v1/alerts/${alertId}`, payload),
  sealClip: (alertId: string) => post<EvidenceClip>(`/api/v1/alerts/${alertId}/seal-clip`),
  getClip: (alertId: string) => get<EvidenceClip>(`/api/v1/alerts/${alertId}/clip`),
  // Video streaming requires the same bearer-token auth as everything else,
  // which a plain <video src> can't attach — fetched as a Blob instead, same
  // pattern as detectionsApi.movementReport.
  clipVideoBlob: (clipId: string) => getBlob(`/api/v1/evidence/clips/${clipId}/video`),
}
