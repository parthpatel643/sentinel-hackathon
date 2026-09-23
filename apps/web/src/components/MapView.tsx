import type { Feature, FeatureCollection, LineString } from 'geojson'
import {
  AttributionControl,
  MapLibreMap,
  Marker,
  NavigationControl,
  type GeoJSONSource,
  type StyleSpecification,
} from 'maplibre-gl'
import { useEffect, useRef } from 'react'
import i18n from '../lib/i18n'

export interface MapMarker {
  id: string
  lat: number
  lon: number
  color: string
  label?: string
  onClick?: () => void
  pulse?: boolean
  /** Shown inside the dot — used by Find a Vehicle's route hops so the map
   * and the timeline list agree on hop order at a glance. */
  number?: number
}

export interface RouteSegment {
  from: [number, number]
  to: [number, number]
  /** false = a "probable" hop (matched by appearance, not plate) — rendered
   * dashed, per docs/03-UX-DESIGN.md \u00a74.4. */
  confirmed: boolean
}

interface MapViewProps {
  markers: MapMarker[]
  center?: [number, number]
  zoom?: number
  className?: string
  routeSegments?: RouteSegment[]
  /** The animated "you are here" marker driven by Replay route. */
  vehiclePosition?: [number, number] | null
  /** The camera onboarding wizard's "click the map to place a pin" step. */
  onMapClick?: (lat: number, lon: number) => void
}

// OpenStreetMap's raw tile server: no API key, global coverage including
// full street-level detail for Ahmedabad specifically (verified by
// downloading tiles directly, not just checking HTTP status). Two earlier
// attempts at other free/no-key providers looked identically blank for two
// entirely different reasons that were then compounded by a real CSS bug
// (the `.maplibregl-map` container was silently forced to `position:
// relative`/`height: 0` by maplibre-gl.css's cascade order — see the inline
// styles below, which is the actual, now-fixed root cause): CARTO's
// basemaps.cartocdn.com returned HTTP 200 for a watermarked "API KEY
// REQUIRED" placeholder tile instead of an error, and Esri's Canvas/*
// services have inconsistent deep-zoom coverage outside the US. OSM's own
// tile usage policy (operations.osmfoundation.org/policies/tiles) does ask
// heavy embedded-app users to run their own tile server rather than hit
// tile.openstreetmap.org directly — acceptable for this hackathon
// dev/demo's traffic level, and attribution is kept visible (rather than
// suppressed) as the policy also requires.
const RASTER_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
}

const GUJARAT_CENTER: [number, number] = [72.5714, 23.0225]
const ROUTE_SOURCE_ID = 'find-a-vehicle-route'

/** Initial compass bearing from point A to B, in degrees — used to orient
 * the DOM-based direction-arrow markers along a route segment. */
function bearingDegrees([lon1, lat1]: [number, number], [lon2, lat2]: [number, number]): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const toDeg = (rad: number) => (rad * 180) / Math.PI
  const y = Math.sin(toRad(lon2 - lon1)) * Math.cos(toRad(lat2))
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(toRad(lon2 - lon1))
  return (toDeg(Math.atan2(y, x)) + 360) % 360
}

function midpoint([lon1, lat1]: [number, number], [lon2, lat2]: [number, number]): [number, number] {
  return [(lon1 + lon2) / 2, (lat1 + lat2) / 2]
}

export function MapView({
  markers,
  center = GUJARAT_CENTER,
  zoom = 11,
  className,
  routeSegments = [],
  vehiclePosition = null,
  onMapClick,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const markerRefs = useRef<Map<string, Marker>>(new Map())
  const arrowMarkersRef = useRef<Marker[]>([])
  const vehicleMarkerRef = useRef<Marker | null>(null)
  const routeSegmentsRef = useRef<RouteSegment[]>(routeSegments)
  routeSegmentsRef.current = routeSegments
  // A ref (not a dependency the click listener effect re-runs on) so the
  // map/click-listener is only ever attached once, but always calls
  // whichever onMapClick the caller most recently passed in.
  const onMapClickRef = useRef(onMapClick)
  onMapClickRef.current = onMapClick

  function syncArrowMarkers(map: MapLibreMap, segments: RouteSegment[]) {
    for (const marker of arrowMarkersRef.current) marker.remove()
    arrowMarkersRef.current = segments.map((segment) => {
      const el = document.createElement('div')
      el.className = 'map-route-arrow'
      el.style.transform = `rotate(${bearingDegrees(segment.from, segment.to) - 90}deg)`
      el.style.opacity = segment.confirmed ? '0.9' : '0.55'
      return new Marker({ element: el }).setLngLat(midpoint(segment.from, segment.to)).addTo(map)
    })
  }

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new MapLibreMap({
      container: containerRef.current,
      style: RASTER_STYLE,
      center,
      zoom,
      attributionControl: false,
      locale: {
        'NavigationControl.ZoomIn': i18n.t('map.zoomIn'),
        'NavigationControl.ZoomOut': i18n.t('map.zoomOut'),
        'AttributionControl.ToggleAttribution': i18n.t('map.toggleAttribution'),
        'Map.Title': i18n.t('map.title'),
      },
    })
    // OSM's tile usage policy requires visible attribution — added
    // explicitly (compact) rather than via the `attributionControl` map
    // option so it can be styled to match the rest of the dark UI instead
    // of MapLibre's default light attribution chip.
    map.addControl(new AttributionControl({ compact: true }), 'bottom-left')
    map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')
    // MapLibre has no public locale setter; relabel controls without losing
    // the current map position or interrupting route replay.
    function updateControlLabels() {
      const labels = [
        ['.maplibregl-ctrl-zoom-in', 'map.zoomIn'],
        ['.maplibregl-ctrl-zoom-out', 'map.zoomOut'],
        ['.maplibregl-ctrl-attrib-button', 'map.toggleAttribution'],
        ['.maplibregl-canvas', 'map.title'],
      ]
      for (const [selector, key] of labels) {
        const element = map.getContainer().querySelector(selector)
        element?.setAttribute('aria-label', i18n.t(key))
        element?.setAttribute('title', i18n.t(key))
      }
    }
    i18n.on('languageChanged', updateControlLabels)
    map.on('click', (event) => onMapClickRef.current?.(event.lngLat.lat, event.lngLat.lng))
    mapRef.current = map

    // The container is sized by a flex layout that may not have its final
    // dimensions on the frame this effect runs — MapLibre reads
    // clientWidth/Height once at construction and never re-checks on its
    // own, which otherwise renders a 0×0 (invisible) canvas. A
    // ResizeObserver keeps the canvas in sync with the real layout.
    const observer = new ResizeObserver(() => map.resize())
    observer.observe(containerRef.current)

    return () => {
      i18n.off('languageChanged', updateControlLabels)
      observer.disconnect()
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const seen = new Set<string>()
    for (const marker of markers) {
      seen.add(marker.id)
      let existing = markerRefs.current.get(marker.id)
      if (!existing) {
        const el = document.createElement(marker.onClick ? 'button' : 'div')
        if (el instanceof HTMLButtonElement) el.type = 'button'
        el.className = 'map-marker'
        existing = new Marker({ element: el }).setLngLat([marker.lon, marker.lat]).addTo(map)
        markerRefs.current.set(marker.id, existing)
      }
      const el = existing.getElement()
      el.style.width = '14px'
      el.style.height = '14px'
      el.style.borderRadius = '50%'
      el.style.background = marker.color
      el.style.border = '2px solid rgba(255,255,255,0.85)'
      el.style.boxShadow = marker.pulse ? `0 0 0 6px ${marker.color}33` : '0 1px 3px rgba(0,0,0,0.5)'
      el.style.cursor = marker.onClick ? 'pointer' : 'default'
      el.title = marker.label ?? marker.id
      el.setAttribute('aria-label', marker.label ?? marker.id)
      el.onclick = marker.onClick ?? null
      el.textContent = marker.number != null ? String(marker.number) : ''
      el.style.display = 'flex'
      el.style.alignItems = 'center'
      el.style.justifyContent = 'center'
      el.style.fontSize = '9px'
      el.style.fontWeight = '700'
      el.style.color = 'white'
      existing.setLngLat([marker.lon, marker.lat])
    }

    for (const [id, marker] of markerRefs.current) {
      if (!seen.has(id)) {
        marker.remove()
        markerRefs.current.delete(id)
      }
    }
  }, [markers])

  // Route polyline (Find a Vehicle's replay map): a GeoJSON source split
  // into per-segment LineString features carrying a `confirmed` property,
  // rendered by two layers (solid vs. dashed) filtered on that property —
  // MapLibre's `line-dasharray` is a per-layer paint property, not
  // per-feature, so a single mixed-confidence route needs two layers to
  // show confirmed and probable hops differently in one line.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    function applyRoute(currentMap: MapLibreMap) {
      const segments = routeSegmentsRef.current
      const geojson: FeatureCollection<LineString, { confirmed: boolean }> = {
        type: 'FeatureCollection',
        features: segments.map(
          (segment): Feature<LineString, { confirmed: boolean }> => ({
            type: 'Feature',
            properties: { confirmed: segment.confirmed },
            geometry: { type: 'LineString', coordinates: [segment.from, segment.to] },
          }),
        ),
      }

      const existingSource = currentMap.getSource(ROUTE_SOURCE_ID) as GeoJSONSource | undefined
      if (existingSource) {
        existingSource.setData(geojson)
      } else {
        currentMap.addSource(ROUTE_SOURCE_ID, { type: 'geojson', data: geojson })
        currentMap.addLayer({
          id: `${ROUTE_SOURCE_ID}-solid`,
          type: 'line',
          source: ROUTE_SOURCE_ID,
          filter: ['==', ['get', 'confirmed'], true],
          paint: { 'line-color': '#5b8cff', 'line-width': 3, 'line-opacity': 0.85 },
        })
        currentMap.addLayer({
          id: `${ROUTE_SOURCE_ID}-dashed`,
          type: 'line',
          source: ROUTE_SOURCE_ID,
          filter: ['==', ['get', 'confirmed'], false],
          paint: {
            'line-color': '#5b8cff',
            'line-width': 3,
            'line-opacity': 0.6,
            'line-dasharray': [2, 1.5],
          },
        })
      }
      syncArrowMarkers(currentMap, segments)
    }

    if (map.isStyleLoaded()) applyRoute(map)
    else map.once('load', () => applyRoute(map))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeSegments])

  // The animated "vehicle" marker driven by Replay route — a single marker
  // whose position the caller updates every animation frame.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (!vehiclePosition) {
      vehicleMarkerRef.current?.remove()
      vehicleMarkerRef.current = null
      return
    }
    if (!vehicleMarkerRef.current) {
      const el = document.createElement('div')
      el.className = 'map-vehicle-marker'
      vehicleMarkerRef.current = new Marker({ element: el }).setLngLat(vehiclePosition).addTo(map)
    } else {
      vehicleMarkerRef.current.setLngLat(vehiclePosition)
    }
  }, [vehiclePosition])

  // Inline styles on the inner div, not Tailwind's `absolute inset-0`
  // utility classes: MapLibre's own stylesheet (maplibre-gl.css, imported
  // in index.css) sets `.maplibregl-map { position: relative }`, and since
  // it loads after Tailwind's generated utilities in the final bundle, it
  // wins the cascade at equal specificity — silently overriding
  // `position: absolute` on that exact element in every browser, which
  // collapsed it to 0 height (inset has no effect without
  // `position: absolute`) and was the real reason the map was blank
  // everywhere, independent of tile provider or WebGL support. Inline
  // styles beat any external stylesheet rule, so this can't recur. The
  // outer div is untouched by maplibre-gl.css (only `.maplibregl-map` is)
  // so the caller's own `absolute inset-0` className works on it as-is —
  // it does not need (and must not get) an inline position of its own,
  // which would just move the same bug up one level.
  return (
    <div className={className}>
      <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
    </div>
  )
}
