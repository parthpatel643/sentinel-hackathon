/** A short two-tone chime for a new watchlist hit or zone event, generated
 * with Web Audio so it needs no asset and works offline. On by default — a
 * control room operator is not always looking at the screen — and mutable
 * from the toolbar. Browsers only allow sound after the page has been
 * interacted with, which signing in always is. */

const STORAGE_KEY = 'sentinel-alert-sound'
let context: AudioContext | null = null

export function alertSoundEnabled(): boolean {
  return localStorage.getItem(STORAGE_KEY) !== 'off'
}

export function setAlertSoundEnabled(enabled: boolean): void {
  localStorage.setItem(STORAGE_KEY, enabled ? 'on' : 'off')
}

export function playAlertTone(): void {
  if (!alertSoundEnabled() || typeof AudioContext === 'undefined') return
  try {
    context ??= new AudioContext()
    const start = context.currentTime
    for (const [offset, frequency] of [[0, 880], [0.18, 660]] as const) {
      const oscillator = context.createOscillator()
      const gain = context.createGain()
      oscillator.type = 'sine'
      oscillator.frequency.value = frequency
      gain.gain.setValueAtTime(0.0001, start + offset)
      gain.gain.exponentialRampToValueAtTime(0.25, start + offset + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, start + offset + 0.16)
      oscillator.connect(gain).connect(context.destination)
      oscillator.start(start + offset)
      oscillator.stop(start + offset + 0.17)
    }
  } catch {
    // Sound is a nicety; never let it break the notifier.
  }
}
