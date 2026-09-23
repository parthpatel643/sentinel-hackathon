import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const variantClasses: Record<Variant, string> = {
  primary: 'bg-accent text-on-accent hover:bg-accent-hover',
  secondary:
    'bg-bg-overlay text-text-primary border border-border-subtle hover:border-border-strong',
  ghost: 'text-text-secondary hover:text-text-primary hover:bg-bg-overlay',
  danger: 'bg-danger-fill text-white hover:brightness-110',
}

const sizeClasses: Record<Size, string> = {
  sm: 'min-h-10 px-3 py-2 text-sm gap-1.5',
  md: 'min-h-11 px-4 py-2.5 text-sm gap-2',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
}

export function Button({ variant = 'primary', size = 'md', className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-md font-medium transition-colors duration-fast',
        'disabled:opacity-40 disabled:pointer-events-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  )
}
