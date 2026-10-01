import { useState } from 'react'
import { Volume2, VolumeX } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { alertSoundEnabled, playAlertTone, setAlertSoundEnabled } from '../../lib/alertSound'

/** Mutes or restores the chime the alert notifier plays on a new hit. Shows
 * the current state, and plays the chime when switched on so the operator
 * hears what to listen for. */
export function AlertSoundToggle() {
  const { t } = useTranslation('readiness')
  const [enabled, setEnabled] = useState(alertSoundEnabled)
  const label = t(enabled ? 'soundOn' : 'soundOff')

  function toggle() {
    const next = !enabled
    setAlertSoundEnabled(next)
    setEnabled(next)
    if (next) playAlertTone()
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={enabled}
      title={label}
      aria-label={label}
      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-text-secondary transition-colors duration-fast hover:bg-bg-overlay hover:text-text-primary"
    >
      {enabled ? <Volume2 size={17} strokeWidth={2.1} /> : <VolumeX size={17} strokeWidth={2.1} />}
    </button>
  )
}
