/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState, useCallback } from 'react'
import { apiJson, getProjectId } from '../lib/api'

const RESOURCE_TYPES = [
  { value: '', label: 'All resource types' },
  { value: 'endpoint', label: 'Endpoint' },
  { value: 'node', label: 'Node' },
]

const SEVERITIES = [
  { value: '', label: 'All severities' },
  { value: 'warning', label: 'Warning' },
  { value: 'critical', label: 'Critical' },
]

export default function SubscriptionManager() {
  const [subscriptions, setSubscriptions] = useState([])
  const [projects, setProjects] = useState([])
  const [projectId, setProjectId] = useState(() => getProjectId() || '')
  const [resourceType, setResourceType] = useState('')
  const [severity, setSeverity] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)

  const fetchSubs = useCallback(async () => {
    try {
      const [subResp, projResp] = await Promise.all([
        apiJson('/api/subscriptions'),
        apiJson('/api/projects'),
      ])
      const projList = projResp.data || []
      setSubscriptions(subResp.data || [])
      setProjects(projList)
      // Validate current projectId exists in the list; if not, fall back to first.
      if (projList.length > 0) {
        const valid = projList.some((p) => p.id === projectId)
        if (!valid) {
          const firstId = projList[0].id
          setProjectId(firstId)
          const { setProjectId: storeSet } = await import('../lib/api')
          storeSet(firstId)
        }
      }
    } catch {
      // backend not ready
    }
  }, [])

  useEffect(() => {
    fetchSubs()
  }, [fetchSubs])

  useEffect(() => {
    if (!error) return
    const timer = setTimeout(() => setError(''), 5000)
    return () => clearTimeout(timer)
  }, [error])

  const create = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await apiJson('/api/subscriptions', {
        method: 'POST',
        body: JSON.stringify({
          project_id: projectId || null,
          resource_type: resourceType || null,
          severity: severity || null,
        }),
      })
      setResourceType('')
      setSeverity('')
      await fetchSubs()
    } catch (err) {
      setError(err.message || 'Failed to create subscription')
    } finally {
      setLoading(false)
    }
  }

  const remove = async (id) => {
    try {
      await apiJson(`/api/subscriptions/${id}`, { method: 'DELETE' })
      await fetchSubs()
    } catch {
      // ignore
    }
  }

  if (subscriptions.length === 0 && !open) {
    return (
      <div className="rounded-lg p-3 mb-3" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <div className="flex items-center justify-between">
          <div>
            <h2 style={{ margin: 0, fontSize: 14 }}>Alert subscriptions</h2>
            <p className="text-xs mt-1" style={{ color: 'var(--gray)' }}>
              Subscribe to receive in-app notifications when alerts fire.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="rounded px-2 py-1 text-xs font-semibold"
            style={{ background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer' }}
          >
            Add subscription
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg p-3 mb-3" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between mb-2">
        <div>
          <h2 style={{ margin: 0, fontSize: 14 }}>Alert subscriptions</h2>
          <p className="text-xs mt-1" style={{ color: 'var(--gray)' }}>
            You will receive in-app notifications when matching alerts fire.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="rounded px-2 py-1 text-xs font-semibold"
          style={{ background: open ? 'transparent' : 'var(--accent)', color: open ? 'var(--gray)' : '#fff', border: open ? '1px solid var(--border)' : 'none', cursor: 'pointer' }}
        >
          {open ? 'Close' : 'Add subscription'}
        </button>
      </div>

      {open && (
        <form onSubmit={create} className="grid grid-cols-1 md:grid-cols-4 gap-2 items-end mb-3 p-3 rounded" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
          <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
            Project
            <select value={projectId} onChange={(e) => setProjectId(e.target.value)} className="rounded px-2 py-1.5 text-xs" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-h)' }}>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.organization_name} / {p.name}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
            Resource type
            <select value={resourceType} onChange={(e) => setResourceType(e.target.value)} className="rounded px-2 py-1.5 text-xs" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-h)' }}>
              {RESOURCE_TYPES.map((rt) => (
                <option key={rt.value} value={rt.value}>{rt.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
            Severity
            <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="rounded px-2 py-1.5 text-xs" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-h)' }}>
              {SEVERITIES.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            disabled={loading || !projectId}
            className="rounded px-2 py-1.5 text-xs font-semibold"
            style={{ background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', opacity: loading ? 0.7 : 1 }}
          >
            Subscribe
          </button>
          {error && <p className="text-xs md:col-span-4 m-0" style={{ color: 'var(--red)' }}>{error}</p>}
        </form>
      )}

      {subscriptions.length > 0 && (
        <div className="grid gap-1">
          {subscriptions.map((sub) => (
            <div key={sub.id} className="flex items-center justify-between rounded px-3 py-1.5 text-xs" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
              <div className="flex items-center gap-2">
                <span style={{ color: 'var(--text-h)' }}>{sub.project_name}</span>
                <span className="rounded px-1 py-0.5" style={{ background: 'var(--accent-bg)', color: 'var(--accent)', fontSize: 9 }}>
                  {sub.resource_type || 'all'}
                </span>
                <span className="rounded px-1 py-0.5" style={{ background: sub.severity === 'critical' ? 'var(--red)' : 'var(--yellow)', color: '#fff', fontSize: 9 }}>
                  {sub.severity || 'all'}
                </span>
              </div>
              <button
                type="button"
                onClick={() => remove(sub.id)}
                className="rounded px-1.5 py-0.5"
                style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--gray)', cursor: 'pointer', fontSize: 9 }}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
