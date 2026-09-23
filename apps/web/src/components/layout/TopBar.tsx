interface TopBarProps {
  title: string
  subtitle?: string
}

export function TopBar({ title, subtitle }: TopBarProps) {
  return (
    <header className="page-heading">
      <h1>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
    </header>
  )
}
