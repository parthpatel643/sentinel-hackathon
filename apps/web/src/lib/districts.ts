import type { Camera } from './types'

/** Gujarat's 34 districts with their headquarters, used only to estimate a
 * camera's district when the registry does not record one. The UI must say
 * "estimated" wherever this is shown. */
export const GUJARAT_DISTRICTS = [
  { name: 'Ahmedabad', lat: 23.0225, lon: 72.5714 },
  { name: 'Amreli', lat: 21.6032, lon: 71.2221 },
  { name: 'Anand', lat: 22.5645, lon: 72.9289 },
  { name: 'Aravalli', lat: 23.4623, lon: 73.2986 },
  { name: 'Banaskantha', lat: 24.1725, lon: 72.4381 },
  { name: 'Bharuch', lat: 21.7051, lon: 72.9959 },
  { name: 'Bhavnagar', lat: 21.7645, lon: 72.1519 },
  { name: 'Botad', lat: 22.1693, lon: 71.6668 },
  { name: 'Chhota Udaipur', lat: 22.3047, lon: 74.013 },
  { name: 'Dahod', lat: 22.835, lon: 74.255 },
  { name: 'Dang', lat: 20.757, lon: 73.6866 },
  { name: 'Devbhumi Dwarka', lat: 22.2028, lon: 69.6528 },
  { name: 'Gandhinagar', lat: 23.2156, lon: 72.6369 },
  { name: 'Gir Somnath', lat: 20.907, lon: 70.3679 },
  { name: 'Jamnagar', lat: 22.4707, lon: 70.0577 },
  { name: 'Junagadh', lat: 21.5222, lon: 70.4579 },
  { name: 'Kheda', lat: 22.6916, lon: 72.8634 },
  { name: 'Kutch', lat: 23.242, lon: 69.6669 },
  { name: 'Mahisagar', lat: 23.1286, lon: 73.61 },
  { name: 'Mehsana', lat: 23.588, lon: 72.3693 },
  { name: 'Morbi', lat: 22.8173, lon: 70.8377 },
  { name: 'Narmada', lat: 21.871, lon: 73.503 },
  { name: 'Navsari', lat: 20.9467, lon: 72.952 },
  { name: 'Panchmahal', lat: 22.7788, lon: 73.6143 },
  { name: 'Patan', lat: 23.8493, lon: 72.1266 },
  { name: 'Porbandar', lat: 21.6417, lon: 69.6293 },
  { name: 'Rajkot', lat: 22.3039, lon: 70.8022 },
  { name: 'Sabarkantha', lat: 23.5986, lon: 72.9659 },
  { name: 'Surat', lat: 21.1702, lon: 72.8311 },
  { name: 'Surendranagar', lat: 22.7271, lon: 71.6486 },
  { name: 'Tapi', lat: 21.1104, lon: 73.3953 },
  { name: 'Vadodara', lat: 22.3072, lon: 73.1812 },
  { name: 'Valsad', lat: 20.5992, lon: 72.9342 },
  { name: 'Vav-Tharad', lat: 24.396, lon: 71.627 },
] as const

export const DISTRICT_COUNT = GUJARAT_DISTRICTS.length

/** Towns whose district the nearest headquarters gets wrong. */
const TOWN_DISTRICTS: Record<string, string> = {
  bilimora: 'Navsari',
  gandhidham: 'Kutch',
  dehgam: 'Gandhinagar',
  adalaj: 'Gandhinagar',
  veraval: 'Gir Somnath',
  somnath: 'Gir Somnath',
}

const MAX_HQ_DISTANCE_KM = 120

function distanceKm(aLat: number, aLon: number, bLat: number, bLon: number) {
  const rad = Math.PI / 180
  const dLat = (bLat - aLat) * rad
  const dLon = (bLon - aLon) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(aLat * rad) * Math.cos(bLat * rad) * Math.sin(dLon / 2) ** 2
  return 6371 * 2 * Math.asin(Math.sqrt(h))
}

function districtFromText(text: string): string | null {
  const lower = text.toLowerCase()
  for (const [town, district] of Object.entries(TOWN_DISTRICTS)) {
    if (lower.includes(town)) return district
  }
  const hit = GUJARAT_DISTRICTS.find((d) => lower.includes(d.name.toLowerCase()))
  return hit?.name ?? null
}

/** A recorded department or name wins; otherwise the nearest district HQ
 * within reach; otherwise null ("no location recorded"). */
export function districtFor(camera: Pick<Camera, 'name' | 'locality' | 'department_name' | 'location'>): string | null {
  const fromText = districtFromText([camera.department_name, camera.locality, camera.name].filter(Boolean).join(' '))
  if (fromText) return fromText
  if (!camera.location) return null
  let best: { name: string; km: number } | null = null
  for (const d of GUJARAT_DISTRICTS) {
    const km = distanceKm(camera.location.lat, camera.location.lon, d.lat, d.lon)
    if (!best || km < best.km) best = { name: d.name, km }
  }
  return best && best.km <= MAX_HQ_DISTANCE_KM ? best.name : null
}

export interface DistrictRollup {
  district: string | null
  cameras: Camera[]
  live: number
  down: number
  degraded: number
  stale: number
  unknown: number
  other: number
}

const STATUS_WEIGHT: Record<string, number> = { down: 0, degraded: 1, stale: 2, connecting: 3, unknown: 4, live: 5 }

/** One row per district, problems first: any Down, then the share that is not
 * live, then size. Cameras with no district sort last. */
export function rollupByDistrict(cameras: Camera[]): DistrictRollup[] {
  const groups = new Map<string | null, Camera[]>()
  for (const camera of cameras) {
    const key = districtFor(camera)
    groups.set(key, [...(groups.get(key) ?? []), camera])
  }
  const rows = [...groups.entries()].map(([district, list]) => ({
    district,
    cameras: [...list].sort((a, b) => (STATUS_WEIGHT[a.status] ?? 4) - (STATUS_WEIGHT[b.status] ?? 4) || a.name.localeCompare(b.name)),
    live: list.filter((c) => c.status === 'live').length,
    down: list.filter((c) => c.status === 'down').length,
    degraded: list.filter((c) => c.status === 'degraded').length,
    stale: list.filter((c) => c.status === 'stale').length,
    unknown: list.filter((c) => c.status === 'unknown').length,
    other: list.filter((c) => c.status === 'connecting').length,
  }))
  return rows.sort((a, b) => {
    if ((a.district === null) !== (b.district === null)) return a.district === null ? 1 : -1
    if (a.down !== b.down) return b.down - a.down
    if (a.degraded !== b.degraded) return b.degraded - a.degraded
    if (a.stale !== b.stale) return b.stale - a.stale
    const aShare = 1 - a.live / a.cameras.length
    const bShare = 1 - b.live / b.cameras.length
    if (aShare !== bShare) return bShare - aShare
    return b.cameras.length - a.cameras.length || (a.district ?? '').localeCompare(b.district ?? '')
  })
}
