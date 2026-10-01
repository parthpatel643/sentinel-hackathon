import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { camerasApi } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import { ApiError } from '../lib/http'
import type { DeviceDiscoveryResult, DeviceDriver } from '../lib/types'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { Input } from './ui/Input'

const DRIVERS: { value: DeviceDriver; labelKey: string }[] = [
  { value: 'onvif', labelKey: 'driverOnvif' },
  { value: 'hikvision', labelKey: 'driverHikvision' },
  { value: 'dahua', labelKey: 'driverDahua' },
]

function errorText(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const detail = (err.detail as { detail?: unknown } | null)?.detail
    if (typeof detail === 'string') return detail
  }
  return fallback
}

/** Onboard every stream an ONVIF camera or NVR exposes from its address and
 * account: list first (nothing written), then add on confirmation. */
export function DeviceDiscoveryForm({ onOnboarded }: { onOnboarded: () => void }) {
  const { t } = useTranslation('readiness')
  const { user } = useAuth()
  const [driver, setDriver] = useState<DeviceDriver>('onvif')
  const [host, setHost] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [departmentName, setDepartmentName] = useState('')
  const [result, setResult] = useState<DeviceDiscoveryResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (user?.role !== 'admin') {
    return <p className="text-xs text-text-tertiary">{t('adminOnly')}</p>
  }

  async function run(dryRun: boolean) {
    setBusy(true)
    setError(null)
    try {
      const response = await camerasApi.discoverDevice({
        driver,
        host: host.trim(),
        username: username || undefined,
        password: password || undefined,
        department_name: departmentName.trim() || undefined,
        dry_run: dryRun,
      })
      setResult(response)
      if (!dryRun) onOnboarded()
    } catch (err) {
      setError(errorText(err, t('deviceError')))
    } finally {
      setBusy(false)
    }
  }

  function edited() {
    setResult(null)
  }

  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-sm font-semibold text-text-primary">{t('deviceTitle')}</h4>
      <p className="text-xs text-text-secondary">{t('deviceHelp')}</p>
      <label className="flex flex-col gap-1 text-xs text-text-secondary">
        {t('driver')}
        <select
          value={driver}
          onChange={(e) => { setDriver(e.target.value as DeviceDriver); edited() }}
          className="h-11 rounded-md border border-border-strong bg-bg-inset px-3 text-sm"
        >
          {DRIVERS.map((d) => <option key={d.value} value={d.value}>{t(d.labelKey)}</option>)}
        </select>
      </label>
      <Input aria-label={t('host')} placeholder={t('host')} value={host} onChange={(e) => { setHost(e.target.value); edited() }} />
      <div className="grid grid-cols-2 gap-2">
        <Input aria-label={t('username')} placeholder={t('username')} autoComplete="off" value={username} onChange={(e) => { setUsername(e.target.value); edited() }} />
        <Input aria-label={t('password')} placeholder={t('password')} type="password" autoComplete="new-password" value={password} onChange={(e) => { setPassword(e.target.value); edited() }} />
      </div>
      <Input aria-label={t('department')} placeholder={t('department')} value={departmentName} onChange={(e) => { setDepartmentName(e.target.value); edited() }} />
      {!result && (
        <Button disabled={!host.trim() || busy} onClick={() => run(true)}>
          {busy ? t('searching') : t('findStreams')}
        </Button>
      )}
      {result && (
        <Card className="max-h-56 overflow-y-auto p-3 text-xs">
          <p className="mb-2 font-medium text-text-primary">
            {result.dry_run
              ? t('streamsFound', { count: result.discovered.length })
              : t('camerasAdded', { count: result.onboarded.length + result.updated.length })}
          </p>
          <ul className="flex flex-col gap-1">
            {result.discovered.map((camera) => (
              <li key={camera.camera_id}>
                <span className="font-medium text-text-primary">{camera.name}</span>{' '}
                <span className="plate-mono text-text-tertiary">{camera.stream_urls[0] ?? ''}</span>
              </li>
            ))}
          </ul>
          {result.failed.map((failure) => (
            <p key={failure.camera_id} className="text-sev-critical">{failure.camera_id}: {failure.error}</p>
          ))}
        </Card>
      )}
      {result?.dry_run && result.discovered.length > 0 && (
        <Button disabled={busy} onClick={() => run(false)}>
          {t('addCameras', { count: result.discovered.length })}
        </Button>
      )}
      {error && <p className="text-xs text-sev-critical">{error}</p>}
    </div>
  )
}
