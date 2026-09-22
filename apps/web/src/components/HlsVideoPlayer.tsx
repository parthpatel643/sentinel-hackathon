import Hls from 'hls.js'
import { useEffect, useRef } from 'react'

interface HlsVideoPlayerProps {
  src: string
  className?: string
}

/** Plays an HLS (.m3u8) URL. Safari has native HLS support built into
 * <video> (no library needed); every other engine needs hls.js to
 * demux/feed segments via Media Source Extensions — detected at runtime
 * rather than assumed, so this works the same regardless of which browser
 * opens the console. `lowLatencyMode` is left off: MediaMTX's LL-HLS output
 * hit a demuxer parse error under hls.js's low-latency path during testing;
 * standard HLS trades a little latency for reliability here. hls.js's own
 * documented pattern for recovering from non-fatal errors (buffer stalls,
 * a dropped segment) is followed rather than treating every ERROR event as
 * fatal — those are expected on a live, looping source. */
export function HlsVideoPlayer({ src, className }: HlsVideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = src
      return
    }

    if (Hls.isSupported()) {
      const hls = new Hls()
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (!data.fatal) return
        switch (data.type) {
          case Hls.ErrorTypes.NETWORK_ERROR:
            hls.startLoad()
            break
          case Hls.ErrorTypes.MEDIA_ERROR:
            hls.recoverMediaError()
            break
          default:
            hls.destroy()
        }
      })
      hls.loadSource(src)
      hls.attachMedia(video)
      return () => hls.destroy()
    }

    return undefined
  }, [src])

  return (
    <video
      ref={videoRef}
      className={className}
      controls
      autoPlay
      muted
      playsInline
      style={{ background: '#000' }}
    />
  )
}
