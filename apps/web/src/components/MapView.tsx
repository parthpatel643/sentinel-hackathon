import {
  AttributionControl,
  MapLibreMap,
  Marker,
  NavigationControl,
  type StyleSpecification,
} from 'maplibre-gl'
import { useEffect, useRef } from 'react'

export interface MapMarker {
  id: string
  lat: number
  lon: number
  color: string
  label?: string
  onClick?: () => void
  pulse?: boolean
}

interface MapViewProps {
  markers: MapMarker[]
  center?: [number, number]
  zoom?: number
  className?: string
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

export function MapView({ markers, center = GUJARAT_CENTER, zoom = 11, className }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const markerRefs = useRef<Map<string, Marker>>(new Map())

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new MapLibreMap({
      container: containerRef.current,
      style: RASTER_STYLE,
      center,
      zoom,
      attributionControl: false,
    })
    // OSM's tile usage policy requires visible attribution — added
    // explicitly (compact) rather than via the `attributionControl` map
    // option so it can be styled to match the rest of the dark UI instead
    // of MapLibre's default light attribution chip.
    map.addControl(new AttributionControl({ compact: true }), 'bottom-left')
    map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')
    mapRef.current = map

    // The container is sized by a flex layout that may not have its final
    // dimensions on the frame this effect runs — MapLibre reads
    // clientWidth/Height once at construction and never re-checks on its
    // own, which otherwise renders a 0×0 (invisible) canvas. A
    // ResizeObserver keeps the canvas in sync with the real layout.
    const observer = new ResizeObserver(() => map.resize())
    observer.observe(containerRef.current)

    return () => {
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
        const el = document.createElement('div')
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
      el.onclick = marker.onClick ?? null
      existing.setLngLat([marker.lon, marker.lat])
    }

    for (const [id, marker] of markerRefs.current) {
      if (!seen.has(id)) {
        marker.remove()
        markerRefs.current.delete(id)
      }
    }
  }, [markers])

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
