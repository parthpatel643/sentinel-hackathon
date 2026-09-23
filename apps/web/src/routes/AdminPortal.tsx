import { useEffect, useState } from 'react'
import { Activity, FileText, Shield, Sliders, Users } from 'lucide-react'
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

type Section = 'users' | 'watchlist' | 'retention' | 'integrations' | 'audit'

const SECTIONS: { id: Section; label: string; icon: typeof Users }[] = [
  { id: 'users', label: 'Users & roles', icon: Users },
  { id: 'watchlist', label: 'Watchlists', icon: Shield },
  { id: 'retention', label: 'Retention & privacy', icon: Sliders },
  { id: 'integrations', label: 'Integrations', icon: Activity },
  { id: 'audit', label: 'Audit log', icon: FileText },
]

function bytesLabel(bytes: number): string {
  if (bytes === 0) return '0 bytes'
  const units = ['bytes', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function UsersSection() {
  const [users, setUsers] = useState<AuthUser[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('operator')

  function load() {
    usersApi
      .list()
      .then(setUsers)
      .catch((err) => setError(err instanceof ApiError ? String(err.detail) : 'Could not load users.'))
  }

  useEffect(load, [])

  async function createUser() {
    setCreating(true)
    setError(null)
    try {
      await usersApi.create({ email, password, full_name: fullName, role })
      setEmail('')
      setFullName('')
      setPassword('')
      setRole('operator')
      load()
    } catch (err) {
      setError(err instanceof ApiError ? String(err.detail) : 'Could not create this user.')
    } finally {
      setCreating(false)
    }
  }

  async function toggleRole(user: AuthUser) {
    await usersApi.update(user.id, { role: user.role === 'admin' ? 'operator' : 'admin' })
    load()
  }

  async function toggleActive(user: AuthUser) {
    await usersApi.update(user.id, { active: !user.active })
    load()
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-4">
        <h3 className="mb-3 text-sm font-semibold text-text-primary">Add a user</h3>
        <div className="grid grid-cols-2 gap-3">
          <Input placeholder="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          <Input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <Input
            type="password"
            placeholder="Temporary password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="h-10 rounded-md border border-border-subtle bg-bg-inset px-3 text-sm text-text-primary"
          >
            <option value="operator">Operator — standard console access</option>
            <option value="admin">Admin — console + this portal</option>
          </select>
        </div>
        <Button
          className="mt-3"
          disabled={creating || !email || !password || !fullName}
          onClick={createUser}
        >
          {creating ? 'Adding…' : 'Add user'}
        </Button>
        {error && <p className="mt-2 text-xs text-sev-critical">{error}</p>}
      </Card>

      <Card className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border-subtle text-xs uppercase tracking-wide text-text-tertiary">
            <tr>
              <th className="px-4 py-2.5 font-medium">Name</th>
              <th className="px-4 py-2.5 font-medium">Email</th>
              <th className="px-4 py-2.5 font-medium">Role</th>
              <th className="px-4 py-2.5 font-medium">Sees</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium" />
            </tr>
          </thead>
          <tbody>
            {users?.map((u) => (
              <tr key={u.id} className="border-b border-border-subtle/60 last:border-0">
                <td className="px-4 py-2.5 text-text-primary">{u.full_name}</td>
                <td className="px-4 py-2.5 text-text-secondary">{u.email}</td>
                <td className="px-4 py-2.5 capitalize text-text-secondary">{u.role}</td>
                <td className="px-4 py-2.5 text-xs text-text-tertiary">
                  {u.role === 'admin'
                    ? 'Operator Console + Admin Portal'
                    : 'Operator Console only (Home, Live Wall, Find a Vehicle, Alerts, Cameras, Health)'}
                </td>
                <td className="px-4 py-2.5">
                  <span className={u.active ? 'text-ok' : 'text-text-tertiary'}>
                    {u.active ? 'Active' : 'Deactivated'}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right">
                  <Button size="sm" variant="ghost" onClick={() => toggleRole(u)}>
                    Make {u.role === 'admin' ? 'operator' : 'admin'}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => toggleActive(u)}>
                    {u.active ? 'Deactivate' : 'Reactivate'}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

function WatchlistSection() {
  const [entries, setEntries] = useState<WatchlistEntry[] | null>(null)

  function load() {
    watchlistApi.list(false).then(setEntries)
  }
  useEffect(load, [])

  async function toggle(entry: WatchlistEntry) {
    await watchlistApi.update(entry.id, !entry.active)
    load()
  }

  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-border-subtle text-xs uppercase tracking-wide text-text-tertiary">
          <tr>
            <th className="px-4 py-2.5 font-medium">Plate</th>
            <th className="px-4 py-2.5 font-medium">Type</th>
            <th className="px-4 py-2.5 font-medium">Priority</th>
            <th className="px-4 py-2.5 font-medium">Valid until</th>
            <th className="px-4 py-2.5 font-medium">Status</th>
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
                {e.valid_until ? new Date(e.valid_until).toLocaleDateString() : 'No expiry'}
              </td>
              <td className={e.active ? 'px-4 py-2.5 text-ok' : 'px-4 py-2.5 text-text-tertiary'}>
                {e.active ? 'Active' : 'Deactivated'}
              </td>
              <td className="px-4 py-2.5 text-right">
                <Button size="sm" variant="ghost" onClick={() => toggle(e)}>
                  {e.active ? 'Deactivate' : 'Reactivate'}
                </Button>
              </td>
            </tr>
          ))}
          {entries?.length === 0 && (
            <tr>
              <td colSpan={6} className="px-4 py-6 text-center text-text-tertiary">
                No watchlist entries yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Card>
  )
}

function RetentionSection() {
  const [detectionsDays, setDetectionsDays] = useState(30)
  const [clipsDays, setClipsDays] = useState(90)
  const [preview, setPreview] = useState<RetentionPreview | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [executing, setExecuting] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  function loadPreview() {
    adminApi.retentionPreview(detectionsDays, clipsDays).then(setPreview)
  }

  useEffect(() => {
    const id = setTimeout(loadPreview, 200)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detectionsDays, clipsDays])

  function executeNow() {
    setExecuting(true)
    setError(null)
    adminApi
      .retentionExecute(detectionsDays, clipsDays)
      .then((r) => {
        setResult(
          `Deleted ${r.detections_deleted.toLocaleString()} detection(s) and ${r.clips_deleted.toLocaleString()} clip(s) (${bytesLabel(r.clips_bytes_deleted)}).`,
        )
        setConfirming(false)
        loadPreview()
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Deletion failed.'))
      .finally(() => setExecuting(false))
  }

  return (
    <Card className="flex flex-col gap-5 p-5">
      <div>
        <div className="mb-1 flex items-center justify-between text-sm">
          <span className="font-medium text-text-primary">Detection reads</span>
          <span className="plate-mono text-text-secondary">{detectionsDays} days</span>
        </div>
        <input
          type="range"
          min={1}
          max={365}
          value={detectionsDays}
          onChange={(e) => setDetectionsDays(Number(e.target.value))}
          className="w-full"
        />
        <p className="mt-1.5 text-xs text-text-tertiary">
          Plate reads older than {detectionsDays} days would be deleted.
          {preview && ` About ${preview.detections_affected.toLocaleString()} detection(s) affected right now.`}
        </p>
      </div>
      <div>
        <div className="mb-1 flex items-center justify-between text-sm">
          <span className="font-medium text-text-primary">Sealed event clips</span>
          <span className="plate-mono text-text-secondary">{clipsDays} days</span>
        </div>
        <input
          type="range"
          min={1}
          max={365}
          value={clipsDays}
          onChange={(e) => setClipsDays(Number(e.target.value))}
          className="w-full"
        />
        <p className="mt-1.5 text-xs text-text-tertiary">
          Sealed clips older than {clipsDays} days would be deleted.
          {preview &&
            ` About ${preview.clips_affected.toLocaleString()} clip(s) affected right now — ${bytesLabel(preview.clips_bytes_affected)}.`}
        </p>
      </div>
      {!confirming ? (
        <Button variant="danger" onClick={() => setConfirming(true)}>
          Delete now
        </Button>
      ) : (
        <div className="rounded-md border border-sev-critical/30 bg-sev-critical/5 p-3">
          <p className="text-sm text-text-primary">
            This permanently deletes the data described above right now — it cannot be undone.
          </p>
          <div className="mt-3 flex gap-2">
            <Button variant="danger" onClick={executeNow} disabled={executing}>
              {executing ? 'Deleting…' : 'Yes, delete permanently'}
            </Button>
            <Button variant="secondary" onClick={() => setConfirming(false)} disabled={executing}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      {result && <p className="text-sm text-ok">{result}</p>}
      {error && <p className="text-sm text-sev-critical">{error}</p>}
      <p className="rounded-md bg-bg-inset px-3 py-2 text-xs text-text-tertiary">
        Every deletion is recorded in the tamper-evident audit log (see the Audit log tab) with who ran it and
        exactly what was removed.
      </p>
    </Card>
  )
}

function IntegrationsSection() {
  const [statuses, setStatuses] = useState<IntegrationStatus[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function load() {
    setLoading(true)
    setError(null)
    adminApi
      .integrations()
      .then(setStatuses)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not reach the integrations check.'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  if (error) {
    return (
      <Card className="p-6 text-center text-sm text-text-tertiary">
        {error}
        <Button variant="secondary" className="mt-3" onClick={load}>
          Retry
        </Button>
      </Card>
    )
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs text-text-tertiary">
          Each card runs a real sample lookup against that provider's driver right now.
        </p>
        <Button variant="secondary" onClick={load} disabled={loading}>
          {loading ? 'Checking…' : 'Recheck'}
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {(statuses ?? []).map((s) => (
          <Card key={s.provider_id} className="p-4">
            <div className="flex items-center justify-between">
              <p className="font-medium text-text-primary">{s.name}</p>
              <span
                className={`rounded-full px-2 py-0.5 text-xs ${
                  s.connected ? 'bg-ok/12 text-ok' : 'bg-sev-critical/12 text-sev-critical'
                }`}
              >
                {s.connected ? 'Connected (mock)' : 'Error'}
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
  const [entries, setEntries] = useState<AuditLogEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [verifying, setVerifying] = useState(false)
  const [verifyResult, setVerifyResult] = useState<string | null>(null)
  const [verifyOk, setVerifyOk] = useState<boolean | null>(null)

  function load() {
    adminApi
      .auditLog()
      .then(setEntries)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load the audit log.'))
  }

  useEffect(load, [])

  function verify() {
    setVerifying(true)
    setVerifyResult(null)
    adminApi
      .verifyAuditLog()
      .then((r) => {
        setVerifyOk(r.intact)
        setVerifyResult(
          r.intact
            ? `Chain intact — ${r.rows_checked.toLocaleString()} row(s) verified.`
            : `Tampering detected at row ${r.first_broken_seq}: ${r.detail}`,
        )
      })
      .catch((e) => {
        setVerifyOk(false)
        setVerifyResult(e instanceof ApiError ? e.message : 'Verification failed.')
      })
      .finally(() => setVerifying(false))
  }

  function detailSummary(entry: AuditLogEntry): string {
    const parts = Object.entries(entry.detail).map(([k, v]) => `${k}: ${String(v)}`)
    return parts.join(', ') || '—'
  }

  if (error) {
    return <Card className="p-6 text-center text-sm text-text-tertiary">{error}</Card>
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex items-center justify-between p-4">
        <div>
          <p className="text-sm font-medium text-text-primary">Tamper-evident audit trail</p>
          <p className="text-xs text-text-tertiary">
            Every sensitive action (face reveals, user changes, watchlist edits, retention deletions) is
            hash-chained — editing any row after the fact breaks every row after it.
          </p>
          {verifyResult && (
            <p className={`mt-1.5 text-xs ${verifyOk ? 'text-ok' : 'text-sev-critical'}`}>{verifyResult}</p>
          )}
        </div>
        <Button variant="secondary" onClick={verify} disabled={verifying}>
          {verifying ? 'Verifying…' : 'Verify integrity'}
        </Button>
      </Card>

      <Card className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border-subtle text-xs uppercase tracking-wide text-text-tertiary">
            <tr>
              <th className="px-4 py-2.5 font-medium">When</th>
              <th className="px-4 py-2.5 font-medium">Actor</th>
              <th className="px-4 py-2.5 font-medium">Action</th>
              <th className="px-4 py-2.5 font-medium">Resource</th>
              <th className="px-4 py-2.5 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody>
            {entries?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-text-tertiary">
                  No audited actions yet.
                </td>
              </tr>
            )}
            {entries?.map((e) => (
              <tr key={e.id} className="border-b border-border-subtle/60 last:border-0">
                <td className="px-4 py-2.5 plate-mono text-xs text-text-tertiary">
                  {new Date(e.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-2.5 text-text-secondary">{e.actor_email ?? '—'}</td>
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
  const [section, setSection] = useState<Section>('users')

  if (user && user.role !== 'admin') {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 text-center">
        <p className="text-sm font-medium text-text-primary">Admin access required</p>
        <p className="text-sm text-text-tertiary">Ask an administrator to grant your account the admin role.</p>
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar title="Admin Portal" subtitle="Departments, users, watchlists & policy" />
      <div className="flex min-h-0 flex-1">
        <nav className="flex w-52 flex-shrink-0 flex-col gap-1 border-r border-border-subtle p-3">
          {SECTIONS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setSection(id)}
              className={
                section === id
                  ? 'flex items-center gap-2 rounded-md bg-accent/15 px-3 py-2 text-sm font-medium text-accent'
                  : 'flex items-center gap-2 rounded-md px-3 py-2 text-sm text-text-secondary hover:bg-bg-overlay'
              }
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </nav>
        <div className="flex-1 overflow-y-auto p-6">
          {section === 'users' && <UsersSection />}
          {section === 'watchlist' && <WatchlistSection />}
          {section === 'retention' && <RetentionSection />}
          {section === 'integrations' && <IntegrationsSection />}
          {section === 'audit' && <AuditSection />}
        </div>
      </div>
    </div>
  )
}
