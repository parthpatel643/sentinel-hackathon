import { useEffect, useRef, useState } from 'react'

/** True while the element is at least partially in the viewport — backs
 * the Live Wall's "only visible tiles stream" rule (docs/03-UX-DESIGN.md
 * §4.3): both a performance requirement and an explicit organiser
 * instruction ("open only cameras you process"). */
export function useInView<T extends HTMLElement>(threshold = 0.1) {
  const ref = useRef<T | null>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold })
    observer.observe(el)
    return () => observer.disconnect()
  }, [threshold])

  return { ref, inView }
}
