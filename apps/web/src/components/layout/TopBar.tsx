import type { FormEvent } from 'react'
import { useState } from 'react'
import { Search } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Input } from '../ui/Input'

interface TopBarProps {
  title: string
  subtitle?: string
}

/** The single most prominent control on every screen — accepts a plate,
 * camera name or place. A plate-shaped string is treated as "find this
 * vehicle" (docs/03-UX-DESIGN.md section 4.2): the eval-day path, one
 * keystroke deep. */
export function TopBar({ title, subtitle }: TopBarProps) {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed) return
    navigate(`/find-a-vehicle?plate=${encodeURIComponent(trimmed)}`)
  }

  return (
    <header className="flex h-14 flex-shrink-0 items-center gap-6 border-b border-border-subtle bg-bg-raised px-6">
      <div className="min-w-0 flex-shrink-0">
        <h1 className="whitespace-nowrap text-base font-semibold text-text-primary">{title}</h1>
        {subtitle && <p className="whitespace-nowrap text-xs text-text-tertiary">{subtitle}</p>}
      </div>
      <form onSubmit={handleSubmit} className="ml-auto w-full max-w-md min-w-[160px]">
        <div className="relative">
          <Search
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary"
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search a plate, camera or place…"
            className="w-full pl-9 plate-mono placeholder:font-ui"
          />
        </div>
      </form>
    </header>
  )
}
