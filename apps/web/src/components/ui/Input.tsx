import type { InputHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'h-10 rounded-md border border-border-subtle bg-bg-inset px-3 text-sm text-text-primary',
        'placeholder:text-text-tertiary focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent',
        className,
      )}
      {...props}
    />
  )
}
