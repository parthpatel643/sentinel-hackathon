/**
 * Camera status colours, in one place.
 *
 * These were previously defined twice — `Home.tsx` in hex and `Cameras.tsx`
 * in oklch — so the same camera status rendered as two different colours
 * depending on which screen you were looking at.
 *
 * The values are tuned for legibility *on a map*, which is a harder problem
 * than a badge on a flat panel: a marker sits on top of roads, parks, water
 * and labels, in both a light and a dark basemap. They are therefore kept
 * bright and saturated (high lightness, real chroma) rather than the muted
 * mid-tones that read well on a solid background but disappear over
 * cartography.
 *
 * Contrast against the basemap itself is handled by the marker's halo in
 * `MapView`, not by the fill colour — see the note there.
 */

import type { CameraStatus } from './types'

export const CAMERA_STATUS_COLOR: Record<CameraStatus, string> = {
  live: 'oklch(0.76 0.18 155)',
  connecting: 'oklch(0.74 0.14 230)',
  degraded: 'oklch(0.79 0.17 70)',
  down: 'oklch(0.68 0.20 25)',
  unknown: 'oklch(0.72 0.03 250)',
}

export function cameraStatusColor(status: string): string {
  return CAMERA_STATUS_COLOR[status as CameraStatus] ?? CAMERA_STATUS_COLOR.unknown
}

/**
 * The name to show a human. Falls back to the catalogue's raw `name` when the
 * API predates `display_name`, and to the id when there is no name at all, so
 * a camera is never rendered nameless.
 */
export function cameraLabel(camera: {
  camera_id: string
  name?: string
  display_name?: string
}): string {
  return camera.display_name || camera.name || camera.camera_id
}

/** `display_name`, with the locality appended when the name carries one. */
export function cameraLabelWithLocality(camera: {
  camera_id: string
  name?: string
  display_name?: string
  locality?: string
}): string {
  const label = cameraLabel(camera)
  return camera.locality ? `${label} · ${camera.locality}` : label
}
