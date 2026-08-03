/* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
import { useEffect, useMemo, useState } from 'react'
import { apiJson, getProjectId, setProjectId } from '../lib/api'
import useAuthStore from '../store/authStore'

const ROLE_OPTIONS = [
  { value: 'viewer', label: 'Read only' },
  { value: 'editor', label: 'Editor' },
]

export default function AccessConsole() {
  const session = useAuthStore((s) => s.session)
  const [projects, setProjects] = useState([])
  const [myRequests, setMyRequests] = useState([])
  const [pendingRequests, setPendingRequests] = useState([])
  const [auditLogs, setAuditLogs] = useState([])
  const [selectedProjectId, setSelectedProjectId] = useState(() => getProjectId() || '')
  const [selectedRole, setSelectedRole] = useState('viewer')
  const [reason, setReason] = useState('')
  const [activeTab, setActiveTab] = useState('request')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const isAdmin = Boolean(session?.user?.is_platform_admin)

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) || null,
    [projects, selectedProjectId],
  )

  const refresh = async () => {
    setLoading(true)
    setError('')
    try {
      const [catalogResp, mineResp, auditResp] = await Promise.all([
        apiJson('/api/projects/catalog'),
        apiJson('/api/access-requests/mine'),
        isAdmin ? apiJson('/api/admin/access-requests') : Promise.resolve({ data: [] }),
      ])
      setProjects(catalogResp.data || [])
      setMyRequests(mineResp.data || [])
      setPendingRequests(auditResp.data || [])
      // Validate selected project still exists; if not, fall back to first.
      const catalog = catalogResp.data || []
      const valid = selectedProjectId && catalog.some((p) => p.id === selectedProjectId)
      if (catalog.length && !valid) {
        setSelectedProjectId(catalog[0].id)
        setProjectId(catalog[0].id)
      }
    } catch (err) {
      setError(err.message || 'Failed to load access console')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [isAdmin])

  // Auto-dismiss status messages after 5 seconds
  useEffect(() => {
    if (!error && !notice) return
    const timer = setTimeout(() => {
      setError('')
      setNotice('')
    }, 5000)
    return () => clearTimeout(timer)
  }, [error, notice])

  useEffect(() => {
    if (!selectedProjectId && !isAdmin) {
      setAuditLogs([])
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const logsResp = await apiJson(
          isAdmin
            ? '/api/audit-logs?limit=25'
            : `/api/audit-logs?project_id=${encodeURIComponent(selectedProjectId)}&limit=25`,
        )
        if (!cancelled) {
          setAuditLogs(logsResp.data || [])
        }
      } catch {
        if (!cancelled) {
          setAuditLogs([])
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isAdmin, selectedProjectId])

  const submitRequest = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    setNotice('')
    try {
      await apiJson('/api/access-requests', {
        method: 'POST',
        body: JSON.stringify({
          project_id: selectedProjectId,
          requested_role: selectedRole,
          reason: reason.trim() || null,
        }),
      })
      setReason('')
      setNotice('Access request submitted')
      await refresh()
    } catch (err) {
      setError(err.message || 'Failed to submit request')
    } finally {
      setLoading(false)
    }
  }

  const reviewRequest = async (requestId, decision) => {
    setLoading(true)
    setError('')
    setNotice('')
    try {
      await apiJson(`/api/admin/access-requests/${requestId}/review`, {
        method: 'POST',
        body: JSON.stringify({ decision }),
      })
      setNotice(`Request ${decision}`)
      await refresh()
    } catch (err) {
      setError(err.message || 'Failed to review request')
    } finally {
      setLoading(false)
    }
  }

  const logProject = isAdmin ? 'all projects' : selectedProject ? selectedProject.name : 'a project'

  return (
    <section className="rounded-lg p-4 mb-3" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between gap-3 mb-3">
        <div>
          <h2 style={{ margin: 0 }}>Access console</h2>
          <p className="text-xs mt-1" style={{ color: 'var(--gray)' }}>
            {isAdmin ? 'Admin reviews access requests and can inspect platform audit logs.' : 'Request project access, then track approval status.'}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {['request', 'requests', isAdmin ? 'pending' : null, 'audit'].filter(Boolean).map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className="rounded px-2 py-1"
              style={{
                background: activeTab === tab ? 'var(--accent-bg)' : 'transparent',
                border: `1px solid ${activeTab === tab ? 'var(--accent)' : 'var(--border)'}`,
                color: activeTab === tab ? 'var(--accent)' : 'var(--gray)',
                cursor: 'pointer',
              }}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {(error || notice) && (
        <div className="mb-3 text-xs rounded px-3 py-2" style={{ border: `1px solid ${error ? 'var(--red)' : 'var(--green)'}`, color: error ? 'var(--red)' : 'var(--green)' }}>
          {error || notice}
        </div>
      )}

      {activeTab === 'request' && (
        <form onSubmit={submitRequest} className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
          <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
            Project
            <select
              required
              value={selectedProjectId}
              onChange={(e) => {
                setSelectedProjectId(e.target.value)
                setProjectId(e.target.value)
                window.location.reload()
              }}
              className="rounded px-3 py-2 text-sm"
              style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-h)' }}
            >
              <option value="" disabled>Select a project</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.organization_name} / {project.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
            Role
            <select
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value)}
              className="rounded px-3 py-2 text-sm"
              style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-h)' }}
            >
              {ROLE_OPTIONS.map((role) => (
                <option key={role.value} value={role.value}>{role.label}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs md:col-span-2" style={{ color: 'var(--gray)' }}>
            Reason
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Describe why you need access"
              className="rounded px-3 py-2 text-sm"
              style={{ background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-h)' }}
            />
          </label>
          <button
            type="submit"
            disabled={loading || !selectedProjectId}
            className="rounded px-3 py-2 text-sm font-semibold"
            style={{ background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', opacity: loading ? 0.7 : 1 }}
          >
            Submit request
          </button>
        </form>
      )}

      {activeTab === 'requests' && (
        <div className="grid gap-2 text-sm">
          {myRequests.length === 0 ? (
            <p className="m-0 text-sm" style={{ color: 'var(--gray)' }}>No access requests yet.</p>
          ) : (
            myRequests.map((request) => (
              <div key={request.id} className="rounded px-3 py-2 flex items-center justify-between" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
                <div>
                  <div>{request.project_name}</div>
                  <div className="text-xs" style={{ color: 'var(--gray)' }}>{request.requested_role} · {request.status}</div>
                </div>
                <div className="text-xs" style={{ color: 'var(--gray)' }}>
                  {request.reviewed_at ? `Reviewed ${request.reviewed_at}` : 'Waiting for approval'}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === 'pending' && isAdmin && (
        <div className="grid gap-2 text-sm">
          {pendingRequests.length === 0 ? (
            <p className="m-0 text-sm" style={{ color: 'var(--gray)' }}>No pending requests.</p>
          ) : (
            pendingRequests.map((request) => (
              <div key={request.id} className="rounded px-3 py-2 flex items-center justify-between gap-3" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
                <div>
                  <div>{request.display_name} · {request.email}</div>
                  <div className="text-xs" style={{ color: 'var(--gray)' }}>{request.project_name} · {request.requested_role}</div>
                  {request.reason && <div className="text-xs mt-1" style={{ color: 'var(--gray)' }}>{request.reason}</div>}
                </div>
                <div className="flex gap-2">
                  <button type="button" onClick={() => reviewRequest(request.id, 'rejected')} className="rounded px-2 py-1 text-xs" style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--gray)', cursor: 'pointer' }}>Reject</button>
                  <button type="button" onClick={() => reviewRequest(request.id, 'approved')} className="rounded px-2 py-1 text-xs" style={{ background: 'var(--accent)', border: 'none', color: '#fff', cursor: 'pointer' }}>Approve</button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {activeTab === 'audit' && (
        <div className="grid gap-2">
          <div className="flex items-center justify-between text-xs" style={{ color: 'var(--gray)' }}>
            <span>Audit scope: {logProject}</span>
            {selectedProjectId && !isAdmin && <span>{selectedProject?.organization_name} / {selectedProject?.name}</span>}
          </div>
          <div className="grid gap-2 max-h-64 overflow-y-auto">
            {auditLogs.length === 0 ? (
              <p className="m-0 text-sm" style={{ color: 'var(--gray)' }}>No audit logs available yet.</p>
            ) : (
              auditLogs.map((entry) => (
                <div key={entry.id} className="rounded px-3 py-2 text-sm" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
                  <div className="flex items-center justify-between gap-3">
                    <span>{entry.action}</span>
                    <span className="text-xs" style={{ color: 'var(--gray)' }}>{entry.created_at}</span>
                  </div>
                  <div className="text-xs mt-1" style={{ color: 'var(--gray)' }}>
                    {entry.resource_type} {entry.resource_id ? `#${entry.resource_id}` : ''} {entry.actor_user_id ? `· actor ${entry.actor_user_id}` : ''}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      <div className="mt-3 text-xs" style={{ color: 'var(--gray)' }}>
        {loading ? 'Refreshing...' : `Projects available: ${projects.length}`}
      </div>
    </section>
  )
}
