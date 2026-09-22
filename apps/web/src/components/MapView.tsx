import { MapLibreMap, Marker, NavigationControl, type StyleSpecification } from 'maplibre-gl'
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

// A free vector-tile basemap needs an API key to look good; rather than ship
// a placeholder key, this uses MapLibre's own no-key demo raster style and
// darkens it with a CSS filter to match the control-room aesthetic
// (docs/03-UX-DESIGN.md's "dark vector basemap" is a documented next step —
// swap for a keyed vector style, e.g. MapTiler/Stadia, in production).
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

  return <div ref={containerRef} className={className} />
}
