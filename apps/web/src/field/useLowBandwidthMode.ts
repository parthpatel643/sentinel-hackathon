import { useState } from 'react'

const KEY = 'sentinel-field-low-bandwidth'

/** docs/03-UX-DESIGN.md §5: "a low-bandwidth mode that suppresses
 * snapshots and shows text-only alerts." A plain on-device preference,
 * not synced anywhere — an officer's own phone knows its own signal. */
export function useLowBandwidthMode() {
  const [enabled, setEnabled] = useState(() => localStorage.getItem(KEY) === 'true')

  function toggle() {
    setEnabled((prev) => {
      const next = !prev
      localStorage.setItem(KEY, String(next))
      return next
    })
  }

  return { enabled, toggle }
}
