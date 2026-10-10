import type { Feature, FeatureCollection, LineString } from 'geojson'
import {
  AttributionControl,
  LngLatBounds,
  MapLibreMap,
  Marker,
  NavigationControl,
  type GeoJSONSource,
  type StyleSpecification,
} from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
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
  /** Text inside the dot, overriding `number` — e.g. "3·4" for two hops at
   * one camera. */
  text?: string
  /** Diameter in px (default 17, or 20 with a number). */
  size?: number
  /** A small always-visible label above the dot ("Start", "Latest"). */
  chip?: string
}

export interface RouteSegment {
  from: [number, number]
  to: [number, number]
  /** false = a "probable" hop (matched by appearance, not plate) — rendered
   * dashed, per docs/03-UX-DESIGN.md \u00a74.4. */
  confirmed: boolean
  /** Position along the route, 0 (first hop) to 1 (latest) — drives the
   * route's colour from earliest to latest. */
  order?: number
}

/** `muted` fades and desaturates the basemap so an overlay (a vehicle's
 * route) is the most prominent thing on the map. */
export type BasemapTone = 'standard' | 'muted'

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
  /** Frame the view on the markers instead of the default Gujarat-wide view.
   * Opt-in: the Cameras and Overview maps deliberately keep a stable
   * statewide frame, but a result set (a plate's sightings) is meaningless
   * if the map is still looking somewhere else. */
  fitToMarkers?: boolean
  /** Centres of registry grid cells no camera covers ([lon, lat]) — the
   * gap-analysis layer on the Cameras map. */
  coverageGaps?: [number, number][]
  basemap?: BasemapTone
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
//
// On a police or venue network the public tile server may be unreachable.
// VITE_MAP_TILE_URL points the basemap at a local or departmental tile
// server instead (any XYZ raster template), and when tiles still fail the
// map says so rather than looking broken: camera pins, routes and gap
// cells are drawn from our own data and remain correct without a basemap.
const TILE_URL = import.meta.env.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTRIBUTION = import.meta.env.VITE_MAP_TILE_ATTRIBUTION || '© OpenStreetMap contributors'
const BASEMAP_SOURCE_ID = 'osm'
const RASTER_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    [BASEMAP_SOURCE_ID]: {
      type: 'raster',
      tiles: [TILE_URL],
      tileSize: 256,
      attribution: TILE_ATTRIBUTION,
    },
  },
  layers: [
    { id: 'basemap-fallback', type: 'background', paint: { 'background-color': '#707782' } },
    { id: 'osm', type: 'raster', source: BASEMAP_SOURCE_ID },
  ],
}

type Theme = 'light' | 'dark'

function currentTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'
}

/** The basemap's look, applied to the raster layer itself rather than as a
 * CSS filter on the whole canvas. A canvas filter also inverted and dulled
 * everything drawn over the tiles — the route line included — which is why a
 * vehicle's route used to blend into the map in the dark theme. Here only the
 * tiles change: dark inverts them (brightness-min above brightness-max) and
 * rotates hue back so water stays blue; `muted` desaturates and lowers
 * contrast so the route is the most prominent thing on screen. */
function basemapPaint(theme: Theme, tone: BasemapTone): Record<string, number> {
  const muted = tone === 'muted'
  if (theme === 'dark') {
    return {
      'raster-brightness-min': muted ? 0.62 : 0.9,
      'raster-brightness-max': muted ? 0.07 : 0.04,
      'raster-hue-rotate': 180,
      'raster-saturation': muted ? -0.85 : -0.1,
      'raster-contrast': muted ? -0.25 : -0.08,
    }
  }
  return {
    'raster-brightness-min': muted ? 0.22 : 0,
    'raster-brightness-max': 1,
    'raster-hue-rotate': 0,
    'raster-saturation': muted ? -0.85 : 0,
    'raster-contrast': muted ? -0.3 : 0,
  }
}

/** The outline under the route: it separates the line from the basemap in
 * either theme. */
function routeCasing(theme: Theme): string {
  return theme === 'dark' ? '#060a14' : '#ffffff'
}

// The route's colour runs from earliest to latest sighting; the same stops
// are used for the stop pins (FindVehicle) and the map legend.
export const ROUTE_START_COLOUR = '#22d3ee'
export const ROUTE_END_COLOUR = '#f59e0b'
const ROUTE_CHEVRON_IMAGE = 'route-chevron'

/** A direction chevron for the route, drawn at runtime so the map needs no
 * sprite or glyph server (it must work with no network beyond the tiles). */
function chevronImage(): ImageData {
  const size = 32
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const g = canvas.getContext('2d')!
  g.lineCap = 'round'
  g.lineJoin = 'round'
  const path = () => {
    g.beginPath()
    g.moveTo(11, 8)
    g.lineTo(21, 16)
    g.lineTo(11, 24)
  }
  g.strokeStyle = 'rgba(10,16,32,0.9)'
  g.lineWidth = 8
  path()
  g.stroke()
  g.strokeStyle = '#ffffff'
  g.lineWidth = 4
  path()
  g.stroke()
  return g.getImageData(0, 0, size, size)
}

const GUJARAT_CENTER: [number, number] = [72.5714, 23.0225]
const ROUTE_SOURCE_ID = 'find-a-vehicle-route'
const GAPS_SOURCE_ID = 'coverage-gaps'
// A stable default: `= []` in the signature is a new array every render, which
// re-ran the gap-layer effect (a GeoJSON reload) on every frame of route replay.
const NO_GAPS: [number, number][] = []

/** Run `apply` as soon as the style accepts sources and layers.
 *
 * Not `isStyleLoaded() ? apply() : once('load', apply)`: `isStyleLoaded()`
 * is also false while basemap *tiles* are loading, and `load` fires only
 * once per map — so an overlay requested after the first load but mid-pan
 * (or on a slow venue network) was queued on an event that never came
 * again, and silently never drawn. `addSource` itself only refuses while the
 * style document is unparsed, which is the one condition worth waiting for. */
function whenStyleReady(map: MapLibreMap, apply: (map: MapLibreMap) => void) {
  try {
    apply(map)
  } catch (error) {
    if (!(error instanceof Error) || !/not done loading/i.test(error.message)) throw error
    map.once('styledata', () => whenStyleReady(map, apply))
  }
}

export function MapView({
  markers,
  center = GUJARAT_CENTER,
  zoom = 11,
  className,
  routeSegments = [],
  vehiclePosition = null,
  onMapClick,
  fitToMarkers = false,
  coverageGaps = NO_GAPS,
  basemap = 'standard',
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const markerRefs = useRef<Map<string, Marker>>(new Map())
  const vehicleMarkerRef = useRef<Marker | null>(null)
  const routeSegmentsRef = useRef<RouteSegment[]>(routeSegments)
  routeSegmentsRef.current = routeSegments
  // A ref (not a dependency the click listener effect re-runs on) so the
  // map/click-listener is only ever attached once, but always calls
  // whichever onMapClick the caller most recently passed in.
  const onMapClickRef = useRef(onMapClick)
  onMapClickRef.current = onMapClick
  const coverageGapsRef = useRef(coverageGaps)
  coverageGapsRef.current = coverageGaps
  const [basemapOffline, setBasemapOffline] = useState(false)
  const [theme, setTheme] = useState<Theme>(currentTheme)
  const { t } = useTranslation('readiness')

  // The basemap follows the operator's theme, which is set on <html>.
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(currentTheme()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

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
    map.on('error', (event) => {
      if ((event as { sourceId?: string }).sourceId === BASEMAP_SOURCE_ID) setBasemapOffline(true)
    })
    map.on('sourcedata', (event) => {
      if (event.sourceId === BASEMAP_SOURCE_ID && event.tile) setBasemapOffline(false)
    })
    mapRef.current = map

    // The container is sized by a flex layout that may not have its final
    // dimensions on the frame this effect runs — MapLibre reads
    // clientWidth/Height once at construction and never re-checks on its
    // own, which otherwise renders a 0×0 (invisible) canvas. A
    // ResizeObserver keeps the canvas in sync with the real layout.
    const observer = new ResizeObserver(() => map.resize())
    observer.observe(containerRef.current)
    // Mutated by the marker effect, never reassigned, so this is the live map.
    const placedMarkers = markerRefs.current

    return () => {
      i18n.off('languageChanged', updateControlLabels)
      observer.disconnect()
      // Markers belong to this map instance. Keeping them in the refs after
      // it is removed made the next map (React StrictMode remounts every
      // effect in development, so `make web` hit this on every visit) treat
      // them as already placed — the registry map rendered with no camera
      // pins at all.
      for (const marker of placedMarkers.values()) marker.remove()
      placedMarkers.clear()
      vehicleMarkerRef.current?.remove()
      vehicleMarkerRef.current = null
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    whenStyleReady(map, (currentMap) => {
      for (const [property, value] of Object.entries(basemapPaint(theme, basemap))) {
        currentMap.setPaintProperty(BASEMAP_SOURCE_ID, property as 'raster-saturation', value)
      }
      const casing = currentMap.getLayer(`${ROUTE_SOURCE_ID}-casing`)
      if (casing) currentMap.setPaintProperty(`${ROUTE_SOURCE_ID}-casing`, 'line-color', routeCasing(theme))
    })
  }, [theme, basemap])

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
      const text = marker.text ?? (marker.number != null ? String(marker.number) : '')
      const size = marker.size ?? (text ? 20 : 17)
      el.style.width = `${size}px`
      el.style.height = `${size}px`
      el.style.borderRadius = '50%'
      el.style.background = marker.color
      // A marker sits on top of cartography, and the basemap follows the
      // operator's theme — so a single light ring (the previous styling)
      // separated the dot from a dark map and vanished against a light one.
      // Two concentric rings fix it in both directions at once: whichever
      // ring matches the basemap, the other one still reads. This is why map
      // pins are conventionally outlined twice rather than just stroked.
      el.style.border = 'none'
      const halo = [
        '0 0 0 2.5px rgba(255,255,255,0.95)',
        '0 0 0 4px rgba(12,16,24,0.55)',
        '0 2px 6px rgba(0,0,0,0.45)',
      ]
      if (marker.pulse) halo.push(`0 0 0 9px color-mix(in oklab, ${marker.color} 28%, transparent)`)
      el.style.boxShadow = halo.join(', ')
      el.style.cursor = marker.onClick ? 'pointer' : 'default'
      el.title = marker.label ?? marker.id
      el.setAttribute('aria-label', marker.label ?? marker.id)
      el.onclick = marker.onClick ?? null
      el.replaceChildren(document.createTextNode(text))
      if (marker.chip) {
        const chip = document.createElement('span')
        chip.className = 'map-marker-chip'
        chip.textContent = marker.chip
        el.appendChild(chip)
      }
      el.style.display = 'flex'
      el.style.alignItems = 'center'
      el.style.justifyContent = 'center'
      el.style.fontSize = size >= 24 ? '11px' : '10px'
      el.style.fontWeight = '700'
      // The numbered route markers carry text on top of the status colour,
      // which is light by design — dark text is what stays readable on it.
      el.style.color = 'oklch(0.22 0.02 250)'
      existing.setLngLat([marker.lon, marker.lat])
    }

    for (const [id, marker] of markerRefs.current) {
      if (!seen.has(id)) {
        marker.remove()
        markerRefs.current.delete(id)
      }
    }
  }, [markers])

  // Frame the view on the markers. A single sighting has no extent to fit,
  // so it gets an explicit centre-and-zoom instead — fitBounds on a
  // zero-area bounding box zooms to maximum and lands on an empty grey tile.
  // Keyed on positions, not on the array: callers rebuild `markers` on every
  // render (every frame of route replay), and re-fitting each time snapped
  // the map back and fought the operator's own zoom and pan.
  const markerPositions = markers.map((m) => `${m.lat.toFixed(5)},${m.lon.toFixed(5)}`).join(';')
  useEffect(() => {
    const map = mapRef.current
    if (!map || !fitToMarkers || markers.length === 0) return

    if (markers.length === 1) {
      map.easeTo({ center: [markers[0].lon, markers[0].lat], zoom: 13, duration: 600 })
      return
    }

    const bounds = new LngLatBounds()
    for (const marker of markers) bounds.extend([marker.lon, marker.lat])
    map.fitBounds(bounds, { padding: 64, maxZoom: 14, duration: 600 })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [markerPositions, fitToMarkers])

  // Route polyline (Find a Vehicle's replay map): a GeoJSON source of
  // per-segment LineStrings carrying `confirmed` and `order`, drawn as a dark
  // casing, a line coloured from earliest to latest, and direction chevrons
  // repeated along it. Probable hops get a dashed layer of their own because
  // `line-dasharray` is per layer, not per feature.
  //
  // Each layer is added if missing on every pass, not once alongside the
  // source: `addSource` can succeed and the first `addLayer` then throw while
  // the style is still loading, and a retry that only checked for the source
  // never added the layers — the route's line silently did not draw.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    function applyRoute(currentMap: MapLibreMap) {
      const segments = routeSegmentsRef.current
      const geojson: FeatureCollection<LineString, { confirmed: boolean; order: number }> = {
        type: 'FeatureCollection',
        features: segments.map(
          (segment): Feature<LineString, { confirmed: boolean; order: number }> => ({
            type: 'Feature',
            properties: { confirmed: segment.confirmed, order: segment.order ?? 1 },
            geometry: { type: 'LineString', coordinates: [segment.from, segment.to] },
          }),
        ),
      }

      const existingSource = currentMap.getSource(ROUTE_SOURCE_ID) as GeoJSONSource | undefined
      if (existingSource) existingSource.setData(geojson)
      else currentMap.addSource(ROUTE_SOURCE_ID, { type: 'geojson', data: geojson })

      if (!currentMap.hasImage(ROUTE_CHEVRON_IMAGE)) {
        currentMap.addImage(ROUTE_CHEVRON_IMAGE, chevronImage(), { pixelRatio: 2 })
      }
      const colour = ['interpolate', ['linear'], ['get', 'order'], 0, ROUTE_START_COLOUR, 1, ROUTE_END_COLOUR]
      const layers: Parameters<MapLibreMap['addLayer']>[0][] = [
        {
          id: `${ROUTE_SOURCE_ID}-casing`,
          type: 'line',
          source: ROUTE_SOURCE_ID,
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': routeCasing(currentTheme()), 'line-width': 9, 'line-opacity': 0.85 },
        },
        {
          id: `${ROUTE_SOURCE_ID}-solid`,
          type: 'line',
          source: ROUTE_SOURCE_ID,
          filter: ['==', ['get', 'confirmed'], true],
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': colour as never, 'line-width': 5 },
        },
        {
          id: `${ROUTE_SOURCE_ID}-dashed`,
          type: 'line',
          source: ROUTE_SOURCE_ID,
          filter: ['==', ['get', 'confirmed'], false],
          paint: { 'line-color': colour as never, 'line-width': 5, 'line-dasharray': [1.4, 1.1] },
        },
        {
          id: `${ROUTE_SOURCE_ID}-chevrons`,
          type: 'symbol',
          source: ROUTE_SOURCE_ID,
          layout: {
            'symbol-placement': 'line',
            'symbol-spacing': 90,
            'icon-image': ROUTE_CHEVRON_IMAGE,
            'icon-size': 1,
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
            'icon-rotation-alignment': 'map',
          },
        },
      ]
      for (const layer of layers) {
        if (!currentMap.getLayer(layer.id)) currentMap.addLayer(layer)
      }
    }

    whenStyleReady(map, applyRoute)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeSegments])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    function applyGaps(currentMap: MapLibreMap) {
      const geojson: FeatureCollection = {
        type: 'FeatureCollection',
        features: coverageGapsRef.current.map((coordinates) => ({
          type: 'Feature',
          properties: {},
          geometry: { type: 'Point', coordinates },
        })),
      }
      const existing = currentMap.getSource(GAPS_SOURCE_ID) as GeoJSONSource | undefined
      if (existing) {
        existing.setData(geojson)
        return
      }
      currentMap.addSource(GAPS_SOURCE_ID, { type: 'geojson', data: geojson })
      currentMap.addLayer({
        id: GAPS_SOURCE_ID,
        type: 'circle',
        source: GAPS_SOURCE_ID,
        paint: {
          'circle-color': '#f59e0b',
          'circle-opacity': 0.5,
          'circle-stroke-width': 0,
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 1.5, 11, 3, 13, 6, 15, 12, 16, 18],
        },
      })
    }

    whenStyleReady(map, applyGaps)
  }, [coverageGaps])

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
      {basemapOffline && (
        <p role="status" className="map-basemap-offline">{t('basemapOffline')}</p>
      )}
    </div>
  )
}
