import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const variantClasses: Record<Variant, string> = {
  primary: 'bg-accent text-on-accent border border-accent hover:bg-accent-hover',
  secondary:
    'bg-bg-raised text-text-primary border border-border-strong hover:border-text-primary',
  ghost: 'text-text-secondary border border-transparent hover:text-text-primary hover:bg-bg-inset hover:border-border-subtle',
  danger: 'bg-danger-fill text-white border border-danger-fill hover:brightness-110',
}

const sizeClasses: Record<Size, string> = {
  sm: 'min-h-9 px-3 py-1.5 text-[13px] gap-1.5',
  md: 'min-h-10 px-4 py-2 text-[13.5px] gap-2',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
}

export function Button({ variant = 'primary', size = 'md', className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center whitespace-nowrap rounded-[10px] font-bold transition-colors duration-fast',
        'disabled:opacity-40 disabled:pointer-events-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  )
}
