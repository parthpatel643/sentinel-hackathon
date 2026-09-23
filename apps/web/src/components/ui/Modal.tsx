import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

interface ModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  children: ReactNode
}

export function Modal({ open, onOpenChange, title, children }: ModalProps) {
  const { t } = useTranslation()
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <Dialog.Content aria-describedby={undefined} className="fixed left-1/2 top-1/2 z-50 flex max-h-[90dvh] w-[min(720px,92vw)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-lg bg-bg-raised shadow-3">
          <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3.5">
            <Dialog.Title className="text-sm font-semibold text-text-primary">{title}</Dialog.Title>
            <Dialog.Close asChild>
              <button
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-text-secondary hover:bg-bg-overlay hover:text-text-primary"
                aria-label={t('common.close')}
              >
                <X size={16} />
              </button>
            </Dialog.Close>
          </div>
          <div className="overflow-y-auto p-5">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
