import { ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { alertsApi } from '../lib/api'
import type { EvidenceClip } from '../lib/types'
import { Modal } from './ui/Modal'

interface SealedClipModalProps {
  clip: EvidenceClip | null
  onClose: () => void
}

/** Plays a sealed evidence clip and shows its hash — docs/01-ARCHITECTURE.md
 * §6.5's tamper-evidence idea made visible: the SHA-256 shown here is
 * computed over the exact bytes the video element is playing, not a
 * separate claim, because both come from the one blob fetched below. */
export function SealedClipModal({ clip, onClose }: SealedClipModalProps) {
  const { t } = useTranslation()
  const [videoUrl, setVideoUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const objectUrlRef = useRef<string | null>(null)

  useEffect(() => {
    if (!clip || clip.status !== 'sealed') {
      setVideoUrl(null)
      return
    }
    let cancelled = false
    alertsApi
      .clipVideoBlob(clip.id)
      .then(({ blob }) => {
        if (cancelled) return
        const url = URL.createObjectURL(blob)
        objectUrlRef.current = url
        setVideoUrl(url)
      })
      .catch(() => !cancelled && setError(t('sealedClip.loadError')))
    return () => {
      cancelled = true
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current)
        objectUrlRef.current = null
      }
    }
  }, [clip, t])

  return (
    <Modal open={clip !== null} onOpenChange={(open) => !open && onClose()} title={t('sealedClip.title')}>
      {clip && (
        <div className="flex flex-col gap-4">
          <div className="aspect-video w-full overflow-hidden rounded-md bg-bg-inset">
            {!videoUrl && !error && (
              <div className="flex h-full items-center justify-center text-sm text-text-tertiary">
                {t('sealedClip.loading')}
              </div>
            )}
            {error && <div className="flex h-full items-center justify-center text-sm text-sev-critical">{error}</div>}
            {videoUrl && (
              <video src={videoUrl} className="h-full w-full" controls autoPlay muted playsInline />
            )}
          </div>
          <div className="flex items-start gap-2 rounded-md bg-bg-inset px-3 py-2.5 text-xs">
            <ShieldCheck size={15} className="mt-0.5 flex-shrink-0 text-ok" />
            <div className="min-w-0">
              <p className="text-text-secondary">
                {clip.sealed_at && t('sealedClip.sealed', { date: new Date(clip.sealed_at).toLocaleString() })}
                {clip.duration_s != null && ` · ${clip.duration_s.toFixed(1)}s`}
              </p>
              <p className="plate-mono mt-0.5 truncate text-text-tertiary">
                {t('sealedClip.sha256', { hash: clip.sha256 })}
              </p>
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}
