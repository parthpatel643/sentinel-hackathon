import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Film, Lock } from 'lucide-react'
import { alertsApi } from '../../lib/api'
import type { Alert, EvidenceClip } from '../../lib/types'

/** Request, follow and open the sealed evidence clip for one alert. Sealing
 * records a real ~10 s window in the background, so a pending clip polls. */
export function ClipAction({ alert, onView }: { alert: Alert; onView: (clip: EvidenceClip) => void }) {
  const { t } = useTranslation()
  const [clip, setClip] = useState<EvidenceClip | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoaded(false)
    setClip(null)
    alertsApi
      .getClip(alert.id)
      .then((c) => !cancelled && setClip(c))
      // 404 means no clip was requested yet: the initial state already says so.
      .catch(() => {})
      .finally(() => !cancelled && setLoaded(true))
    return () => {
      cancelled = true
    }
  }, [alert.id])

  useEffect(() => {
    if (clip?.status !== 'pending') return
    let cancelled = false
    const id = setInterval(() => {
      alertsApi.getClip(alert.id).then((result) => { if (!cancelled) setClip(result) }).catch(() => {})
    }, 2000)
    return () => { cancelled = true; clearInterval(id) }
  }, [alert.id, clip?.status])

  async function requestSeal() {
    setBusy(true)
    setError(false)
    try {
      setClip(await alertsApi.sealClip(alert.id))
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }

  if (!loaded) return <button type="button" className="gb-btn" disabled><Lock className="gb-ico" aria-hidden="true" />{t('alerts.sealClip')}</button>

  if (!clip || clip.status === 'failed') {
    return (
      <span className="gb-clip">
        <button type="button" className="gb-btn" onClick={requestSeal} disabled={busy}>
          <Lock className="gb-ico" aria-hidden="true" />{t(busy ? 'alerts.sealingClip' : 'alerts.sealClip')}
        </button>
        {(clip?.status === 'failed' || error) && <span role="alert" className="gb-clip-error">{t('alerts.sealingFailed')}</span>}
      </span>
    )
  }

  if (clip.status === 'pending') {
    return <button type="button" className="gb-btn" disabled><Film className="gb-ico" aria-hidden="true" />{t('alerts.sealingClip')}</button>
  }

  return <button type="button" className="gb-btn" onClick={() => onView(clip)}><Film className="gb-ico" aria-hidden="true" />{t('alerts.watchSealedClip')}</button>
}
