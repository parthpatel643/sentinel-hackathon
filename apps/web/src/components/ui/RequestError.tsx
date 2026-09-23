import { useTranslation } from 'react-i18next'
import { Button } from './Button'

export function RequestError({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation()
  return (
    <div role="alert" className="request-error">
      <p>{t('workspace.refreshError')}</p>
      <Button variant="ghost" size="sm" onClick={onRetry}>{t('common.retry')}</Button>
    </div>
  )
}
