import { useEffect, useRef, useState } from 'react'
import { Activity, ArrowRight, FileText, Plus, Search, Shield, Sliders, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { TopBar } from '../components/layout/TopBar'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { adminApi, usersApi, watchlistApi } from '../lib/api'
import { useAuth } from '../lib/AuthContext'
import { ApiError } from '../lib/http'
import type {
  AuditLogEntry,
  AuthUser,
  IntegrationStatus,
  RetentionPreview,
  WatchlistEntry,
} from '../lib/types'
import './management-workspace.css'

type Section = 'users' | 'watchlist' | 'retention' | 'integrations' | 'audit'

const SECTION_ICONS: Record<Section, typeof Users> = {
  users: Users,
  watchlist: Shield,
  retention: Sliders,
  integrations: Activity,
  audit: FileText,
}

const SECTIONS: Section[] = ['users', 'watchlist', 'retention', 'integrations', 'audit']

function bytesLabel(bytes: number): string {
  if (bytes === 0) return '0 bytes'
  const units = ['bytes', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function UsersSection() {
  const { t } = useTranslation()
  const [users, setUsers] = useState<AuthUser[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('operator')
  const [showCreate, setShowCreate] = useState(false)
  const [filter, setFilter] = useState('')
  const [busyUser, setBusyUser] = useState<string | null>(null)

  function load() {
    setError(null)
    usersApi
      .list()
      .then(setUsers)
      .catch((err) => setError(err instanceof ApiError ? String(err.detail) : t('admin.users.loadError')))
  }

  useEffect(load, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function createUser() {
    setCreating(true)
    setError(null)
    try {
      await usersApi.create({ email, password, full_name: fullName, role })
      setEmail('')
      setFullName('')
      setPassword('')
      setRole('operator')
      setShowCreate(false)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : t('admin.users.createError'))
    } finally {
      setCreating(false)
    }
  }

  async function toggleRole(user: AuthUser) {
    setBusyUser(user.id)
    setError(null)
    try {
      await usersApi.update(user.id, { role: user.role === 'admin' ? 'operator' : 'admin' })
      load()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : t('management:actionError'))
    } finally {
      setBusyUser(null)
    }
  }

  async function toggleActive(user: AuthUser) {
    setBusyUser(user.id)
    setError(null)
    try {
      await usersApi.update(user.id, { active: !user.active })
      load()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : t('management:actionError'))
    } finally {
      setBusyUser(null)
    }
  }

  const visibleUsers = users?.filter((user) => `${user.full_name} ${user.email} ${user.role}`.toLowerCase().includes(filter.toLowerCase()))

  return (
    <div className="management-register">
      <div className="management-register-toolbar">
        <div>
          <h3>{t('management:accessRegister')}</h3>
          <p>{users ? `${t('management:userCount', { count: users.length })} · ${t('management:activeCount', { count: users.filter((u) => u.active).length })}` : t(error ? 'management:unavailable' : 'common.loading')}</p>
        </div>
        <Button onClick={() => setShowCreate((value) => !value)} aria-expanded={showCreate} aria-controls="create-user-form">
          <Plus size={16} aria-hidden="true" />{showCreate ? t('management:cancel') : t('management:addUser')}
        </Button>
      </div>
      {error && <div role="alert" className="management-error">{error}<Button variant="ghost" onClick={load}>{t('common.retry')}</Button></div>}
      {showCreate && <Card className="management-create p-5">
        <h3 className="mb-3 text-sm font-semibold text-text-primary">{t('admin.users.addUser')}</h3>
        <form id="create-user-form" onSubmit={(event) => { event.preventDefault(); void createUser() }}>
        <div className="management-form-grid">
          <label>{t('management:fullName')}
          <Input
            required
            placeholder={t('admin.users.fullNamePlaceholder')}
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
          </label>
          <label>{t('management:email')}
          <Input required type="email" placeholder={t('admin.users.emailPlaceholder')} value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label>{t('management:password')}
          <Input
            required
            type="password"
            placeholder={t('admin.users.passwordPlaceholder')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          </label>
          <label>{t('management:role')}
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="h-10 rounded-md border border-border-subtle bg-bg-inset px-3 text-sm text-text-primary"
          >
            <option value="operator">{t('admin.users.roleOperator')}</option>
            <option value="admin">{t('admin.users.roleAdmin')}</option>
          </select>
          </label>
        </div>
        <Button
          className="mt-3"
          disabled={creating || !email || !password || !fullName}
          type="submit"
        >
          {creating ? t('admin.users.adding') : t('admin.users.add')}
        </Button>
        </form>
      </Card>}

      <label className="management-search">
        <Search size={17} aria-hidden="true" />
        <input type="search" aria-label={t('management:filterUsers')} placeholder={t('management:filterUsers')} value={filter} onChange={(event) => setFilter(event.target.value)} />
      </label>
      <Card className="management-table overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border-subtle text-xs uppercase tracking-wide text-text-tertiary">
            <tr>
              <th className="px-4 py-2.5 font-medium">{t('admin.users.columns.name')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.users.columns.email')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.users.columns.role')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.users.columns.sees')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.users.columns.status')}</th>
              <th className="px-4 py-2.5 font-medium" />
            </tr>
          </thead>
          <tbody>
            {visibleUsers?.map((u) => (
              <tr key={u.id} className="border-b border-border-subtle/60 last:border-0">
                <td className="px-4 py-2.5 text-text-primary">{u.full_name}</td>
                <td className="px-4 py-2.5 text-text-secondary">{u.email}</td>
                <td className="px-4 py-2.5 capitalize text-text-secondary">{u.role}</td>
                <td className="px-4 py-2.5 text-xs text-text-tertiary">
                  {u.role === 'admin' ? t('admin.users.seesAdmin') : t('admin.users.seesOperator')}
                </td>
                <td className="px-4 py-2.5">
                  <span className={u.active ? 'text-ok' : 'text-text-tertiary'}>
                    {u.active ? t('common.active') : t('common.deactivated')}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right">
                  <Button size="sm" variant="ghost" disabled={busyUser === u.id} onClick={() => toggleRole(u)}>
                    {u.role === 'admin' ? t('admin.users.makeOperator') : t('admin.users.makeAdmin')}
                  </Button>
                  <Button size="sm" variant="ghost" disabled={busyUser === u.id} onClick={() => toggleActive(u)}>
                    {u.active ? t('admin.users.deactivate') : t('admin.users.reactivate')}
                  </Button>
                </td>
              </tr>
            ))}
            {visibleUsers?.length === 0 && <tr><td colSpan={6} className="management-empty">{t('management:noUsers')}</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

function WatchlistSection() {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<WatchlistEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  function load() {
    setError(null)
    watchlistApi.list(false).then(setEntries).catch((err) => setError(err instanceof ApiError ? String(err.detail) : t('workspace.refreshError')))
  }
  useEffect(load, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function toggle(entry: WatchlistEntry) {
    setBusy(entry.id)
    setError(null)
    try {
      await watchlistApi.update(entry.id, !entry.active)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : t('management:actionError'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="management-register">
    <div className="management-register-toolbar">
      <p>{entries ? `${t('management:records', { count: entries.length })} · ${t('management:activeCount', { count: entries.filter((entry) => entry.active).length })}` : t(error ? 'management:unavailable' : 'common.loading')}</p>
      <Button variant="secondary" onClick={load}>{t('admin.integrations.recheck')}</Button>
    </div>
    {error && <p role="alert" className="management-error">{error}</p>}
    <Card className="management-table overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-border-subtle text-xs uppercase tracking-wide text-text-tertiary">
          <tr>
            <th className="px-4 py-2.5 font-medium">{t('admin.watchlist.columns.plate')}</th>
            <th className="px-4 py-2.5 font-medium">{t('admin.watchlist.columns.type')}</th>
            <th className="px-4 py-2.5 font-medium">{t('admin.watchlist.columns.priority')}</th>
            <th className="px-4 py-2.5 font-medium">{t('admin.watchlist.columns.validUntil')}</th>
            <th className="px-4 py-2.5 font-medium">{t('admin.watchlist.columns.status')}</th>
            <th className="px-4 py-2.5 font-medium" />
          </tr>
        </thead>
        <tbody>
          {entries?.map((e) => (
            <tr key={e.id} className="border-b border-border-subtle/60 last:border-0">
              <td className="plate-mono px-4 py-2.5 text-text-primary">{e.plate_normalised}</td>
              <td className="px-4 py-2.5 text-text-secondary">{e.entry_type}</td>
              <td className="px-4 py-2.5 capitalize text-text-secondary">{e.priority}</td>
              <td className="px-4 py-2.5 text-text-tertiary">
                {e.valid_until ? new Date(e.valid_until).toLocaleDateString() : t('common.noExpiry')}
              </td>
              <td className={e.active ? 'px-4 py-2.5 text-ok' : 'px-4 py-2.5 text-text-tertiary'}>
                {e.active ? t('common.active') : t('common.deactivated')}
              </td>
              <td className="px-4 py-2.5 text-right">
                <Button size="sm" variant="ghost" disabled={busy === e.id} onClick={() => toggle(e)}>
                  {e.active ? t('admin.watchlist.deactivate') : t('admin.watchlist.reactivate')}
                </Button>
              </td>
            </tr>
          ))}
          {entries?.length === 0 && (
            <tr>
              <td colSpan={6} className="px-4 py-6 text-center text-text-tertiary">
                {t('admin.watchlist.noEntries')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Card>
    </div>
  )
}

function RetentionSection() {
  const { t } = useTranslation()
  const [detectionsDays, setDetectionsDays] = useState(30)
  const [clipsDays, setClipsDays] = useState(90)
  const [preview, setPreview] = useState<RetentionPreview | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [executing, setExecuting] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const previewVersion = useRef(0)

  function loadPreview() {
    const version = ++previewVersion.current
    setPreview(null)
    setError(null)
    adminApi.retentionPreview(detectionsDays, clipsDays)
      .then((next) => { if (version === previewVersion.current) setPreview(next) })
      .catch((err) => { if (version === previewVersion.current) setError(err instanceof ApiError ? String(err.detail) : t('workspace.refreshError')) })
  }

  function changePeriod(kind: 'detections' | 'clips', days: number) {
    previewVersion.current += 1
    setPreview(null)
    setConfirming(false)
    setResult(null)
    if (kind === 'detections') setDetectionsDays(days)
    else setClipsDays(days)
  }

  useEffect(() => {
    const id = setTimeout(loadPreview, 200)
    return () => { clearTimeout(id); previewVersion.current += 1 }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detectionsDays, clipsDays])

  function executeNow() {
    setExecuting(true)
    setError(null)
    adminApi
      .retentionExecute(detectionsDays, clipsDays)
      .then((r) => {
        setResult(
          t('admin.retention.deletedSummary', {
            detections: r.detections_deleted.toLocaleString(),
            clips: r.clips_deleted.toLocaleString(),
            size: bytesLabel(r.clips_bytes_deleted),
          }),
        )
        setConfirming(false)
        loadPreview()
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : t('admin.retention.deletionFailed')))
      .finally(() => setExecuting(false))
  }

  return (
    <div className="management-retention">
    <Card className="flex flex-col gap-5 p-5">
      <div>
        <div className="mb-1 flex items-center justify-between text-sm">
          <span className="font-medium text-text-primary">{t('admin.retention.detectionReads')}</span>
          <span className="plate-mono text-text-secondary">{t('admin.retention.days', { count: detectionsDays })}</span>
        </div>
        <input
          aria-label={t('admin.retention.detectionReads')}
          type="range"
          min={1}
          max={365}
          value={detectionsDays}
          disabled={executing}
          onChange={(e) => changePeriod('detections', Number(e.target.value))}
          className="w-full"
        />
        <p className="mt-1.5 text-xs text-text-tertiary">
          {t('admin.retention.detectionsHelp', { count: detectionsDays })}
          {preview && t('admin.retention.detectionsAffected', { count: preview.detections_affected.toLocaleString() })}
        </p>
      </div>
      <div>
        <div className="mb-1 flex items-center justify-between text-sm">
          <span className="font-medium text-text-primary">{t('admin.retention.sealedClips')}</span>
          <span className="plate-mono text-text-secondary">{t('admin.retention.days', { count: clipsDays })}</span>
        </div>
        <input
          aria-label={t('admin.retention.sealedClips')}
          type="range"
          min={1}
          max={365}
          value={clipsDays}
          disabled={executing}
          onChange={(e) => changePeriod('clips', Number(e.target.value))}
          className="w-full"
        />
        <p className="mt-1.5 text-xs text-text-tertiary">
          {t('admin.retention.clipsHelp', { count: clipsDays })}
          {preview &&
            t('admin.retention.clipsAffected', {
              count: preview.clips_affected.toLocaleString(),
              size: bytesLabel(preview.clips_bytes_affected),
            })}
        </p>
      </div>
      {!confirming ? (
        <Button variant="danger" disabled={!preview || Boolean(error)} onClick={() => setConfirming(true)}>
          {t('admin.retention.deleteNow')}
        </Button>
      ) : (
        <div className="rounded-md border border-sev-critical/30 bg-sev-critical/5 p-3">
          <p className="text-sm text-text-primary">{t('admin.retention.confirmMessage')}</p>
          <div className="mt-3 flex gap-2">
            <Button variant="danger" onClick={executeNow} disabled={executing || !preview}>
              {executing ? t('admin.retention.deleting') : t('admin.retention.confirmDelete')}
            </Button>
            <Button variant="secondary" onClick={() => setConfirming(false)} disabled={executing}>
              {t('admin.retention.cancel')}
            </Button>
          </div>
        </div>
      )}
      {result && <p className="text-sm text-ok">{result}</p>}
      {error && <div role="alert" className="text-sm text-sev-critical">{error}<Button variant="ghost" onClick={loadPreview}>{t('common.retry')}</Button></div>}
      <p className="rounded-md bg-bg-inset px-3 py-2 text-xs text-text-tertiary">{t('admin.retention.auditNotice')}</p>
    </Card>
    <section className="management-preview" aria-label={t('management:preview')}>
      <h3>{t('management:preview')}</h3>
      <p>{t('management:previewHelp')}</p>
      <dl>
        <div><dt>{t('management:detections')}</dt><dd>{preview?.detections_affected.toLocaleString() ?? t('management:unavailable')}</dd></div>
        <div><dt>{t('management:clips')}</dt><dd>{preview?.clips_affected.toLocaleString() ?? t('management:unavailable')}</dd></div>
        <div><dt>{t('management:storage')}</dt><dd>{preview ? bytesLabel(preview.clips_bytes_affected) : t('management:unavailable')}</dd></div>
      </dl>
    </section>
    </div>
  )
}

function IntegrationsSection() {
  const { t } = useTranslation()
  const [statuses, setStatuses] = useState<IntegrationStatus[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function load() {
    setLoading(true)
    setError(null)
    adminApi
      .integrations()
      .then(setStatuses)
      .catch((e) => setError(e instanceof ApiError ? e.message : t('admin.integrations.loadError')))
      .finally(() => setLoading(false))
  }

  useEffect(load, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    return (
      <Card className="p-6 text-center text-sm text-text-tertiary">
        {error}
        <Button variant="secondary" className="mt-3" onClick={load}>
          {t('admin.integrations.retry')}
        </Button>
      </Card>
    )
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs text-text-tertiary">{t('admin.integrations.description')}</p>
        <Button variant="secondary" onClick={load} disabled={loading}>
          {loading ? t('admin.integrations.checking') : t('admin.integrations.recheck')}
        </Button>
      </div>
      {loading && !statuses && <p role="status" className="management-empty">{t('common.loading')}</p>}
      {!loading && statuses?.length === 0 && <p className="management-empty">{t('management:noIntegrations')}</p>}
      <div className="management-integrations">
        {(statuses ?? []).map((s) => (
          <Card key={s.provider_id} className="p-5">
            <div className="flex items-center justify-between">
              <p className="font-medium text-text-primary">{s.name}</p>
              <span
                className={`rounded-full px-2 py-0.5 text-xs ${
                  s.connected ? 'bg-ok/12 text-ok' : 'bg-sev-critical/12 text-sev-critical'
                }`}
              >
                {s.connected ? t('admin.integrations.connected') : t('admin.integrations.error')}
              </span>
            </div>
            <p className="mt-1 text-xs text-text-tertiary">{s.description}</p>
            <p className="mt-3 text-xs text-text-tertiary">{s.detail}</p>
            <p className="mt-2 plate-mono text-[11px] text-text-tertiary">
              {s.sample_operation}
              {s.sample_latency_ms !== null && ` — ${s.sample_latency_ms.toFixed(1)}ms`}
            </p>
          </Card>
        ))}
      </div>
    </div>
  )
}

function AuditSection() {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<AuditLogEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [verifying, setVerifying] = useState(false)
  const [verifyResult, setVerifyResult] = useState<string | null>(null)
  const [verifyOk, setVerifyOk] = useState<boolean | null>(null)

  function load() {
    adminApi
      .auditLog()
      .then(setEntries)
      .catch((e) => setError(e instanceof ApiError ? e.message : t('admin.audit.loadError')))
  }

  useEffect(load, []) // eslint-disable-line react-hooks/exhaustive-deps

  function verify() {
    setVerifying(true)
    setVerifyResult(null)
    adminApi
      .verifyAuditLog()
      .then((r) => {
        setVerifyOk(r.intact)
        setVerifyResult(
          r.intact
            ? t('admin.audit.chainIntact', { count: r.rows_checked.toLocaleString() })
            : t('admin.audit.tamperingDetected', { row: r.first_broken_seq, detail: r.detail }),
        )
      })
      .catch((e) => {
        setVerifyOk(false)
        setVerifyResult(e instanceof ApiError ? e.message : t('admin.audit.verificationFailed'))
      })
      .finally(() => setVerifying(false))
  }

  function detailSummary(entry: AuditLogEntry): string {
    const parts = Object.entries(entry.detail).map(([k, v]) => `${k}: ${String(v)}`)
    return parts.join(', ') || t('common.unknown')
  }

  if (error) {
    return <Card className="p-6 text-center text-sm text-text-tertiary"><p role="alert">{error}</p><Button variant="secondary" onClick={() => { setError(null); load() }}>{t('common.retry')}</Button></Card>
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-wrap items-center justify-between gap-4 p-5">
        <div>
          <p className="text-sm font-medium text-text-primary">{t('admin.audit.title')}</p>
          <p className="text-xs text-text-tertiary">{t('admin.audit.description')}</p>
          {verifyResult && (
            <p className={`mt-1.5 text-xs ${verifyOk ? 'text-ok' : 'text-sev-critical'}`}>{verifyResult}</p>
          )}
        </div>
        <Button variant="secondary" onClick={verify} disabled={verifying}>
          {verifying ? t('admin.audit.verifying') : t('admin.audit.verifyIntegrity')}
        </Button>
      </Card>

      <Card className="management-table overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border-subtle text-xs uppercase tracking-wide text-text-tertiary">
            <tr>
              <th className="px-4 py-2.5 font-medium">{t('admin.audit.columns.when')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.audit.columns.actor')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.audit.columns.action')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.audit.columns.resource')}</th>
              <th className="px-4 py-2.5 font-medium">{t('admin.audit.columns.detail')}</th>
            </tr>
          </thead>
          <tbody>
            {entries?.length === 0 && <tr><td colSpan={5} className="management-empty">{t('management:noAudit')}</td></tr>}
            {entries?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">
                  {t('admin.audit.noEntries')}
                </td>
              </tr>
            )}
            {entries?.map((e) => (
              <tr key={e.id} className="border-b border-border-subtle/60 last:border-0">
                <td className="px-4 py-2.5 plate-mono text-xs text-text-tertiary">
                  {new Date(e.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-2.5 text-text-secondary">{e.actor_email ?? t('common.unknown')}</td>
                <td className="px-4 py-2.5 text-text-primary">{e.action}</td>
                <td className="px-4 py-2.5 text-xs text-text-tertiary">
                  {e.resource_type}
                  {e.resource_id ? ` / ${e.resource_id}` : ''}
                </td>
                <td className="px-4 py-2.5 text-xs text-text-tertiary">{detailSummary(e)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

export function AdminPortal() {
  const { user } = useAuth()
  const { t } = useTranslation()
  const [section, setSection] = useState<Section>('users')

  if (user && user.role !== 'admin') {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 text-center">
        <p className="text-sm font-medium text-text-primary">{t('admin.accessRequired')}</p>
        <p className="text-sm text-text-tertiary">{t('admin.askAdmin')}</p>
      </div>
    )
  }

  return (
    <div className="management-workspace flex min-h-0 flex-1 flex-col">
      <TopBar title={t('nav.admin')} subtitle={t('admin.subtitle')} />
      <div className="page-body management-body">
        <div className="management-heading">
          <div><h2>{t('management:adminTitle')}</h2><p>{t('management:adminIntro')}</p></div>
          <Shield size={34} strokeWidth={1.5} aria-hidden="true" />
        </div>
        <nav aria-label={t('workspace.adminNavigation')} className="management-navigation">
          {SECTIONS.map((id) => {
            const Icon = SECTION_ICONS[id]
            return (
              <button
                key={id}
                aria-label={t(`admin.sections.${id}`)}
                onClick={() => setSection(id)}
                aria-current={section === id ? 'page' : undefined}
                className={section === id ? 'is-current' : ''}
              >
                <Icon size={20} aria-hidden="true" />
                <span>{t(`admin.sections.${id}`)}</span>
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            )
          })}
        </nav>
        <section className="management-section" aria-labelledby="management-section-heading">
          <header className="management-section-heading">
            <h2 id="management-section-heading">{t(`admin.sections.${section}`)}</h2>
            <p>{t(`management:${section}Help`)}</p>
          </header>
          {section === 'users' && <UsersSection />}
          {section === 'watchlist' && <WatchlistSection />}
          {section === 'retention' && <RetentionSection />}
          {section === 'integrations' && <IntegrationsSection />}
          {section === 'audit' && <AuditSection />}
        </section>
        <p className="management-footnote"><Shield size={16} aria-hidden="true" />{t('management:adminNote')}</p>
      </div>
    </div>
  )
}
