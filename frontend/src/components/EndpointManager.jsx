import { useState, useEffect } from 'react'
import useMetricsStore from '../store/metricsStore'

export default function EndpointManager() {
  const endpoints = useMetricsStore((s) => s.endpoints)
  const fetchEndpoints = useMetricsStore((s) => s.fetchEndpoints)
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState(null)
  const [name, setName] = useState('')
  const [targetHost, setTargetHost] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchEndpoints()
  }, [fetchEndpoints])

  const resetForm = () => {
    setName('')
    setTargetHost('')
    setEditId(null)
    setShowForm(false)
    setError('')
  }

  const openCreate = () => {
    resetForm()
    setShowForm(true)
  }

  const openEdit = (ep) => {
    setName(ep.name)
    setTargetHost(ep.target_host)
    setEditId(ep.id)
    setShowForm(true)
    setError('')
  }

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const url = editId ? `/api/endpoints/${editId}` : '/api/endpoints'
      const method = editId ? 'PUT' : 'POST'
      const resp = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), target_host: targetHost.trim() }),
      })
      const json = await resp.json()
      if (!json.success) {
        setError(json.error?.message || 'Save failed')
        return
      }
      fetchEndpoints()
      resetForm()
    } catch {
      setError('Network error')
    } finally {
      setSaving(false)
    }
  }

  const doDelete = async (ep) => {
    if (!window.confirm(`Delete endpoint "${ep.name}" (${ep.target_host})?`)) return
    try {
      await fetch(`/api/endpoints/${ep.id}`, { method: 'DELETE' })
      fetchEndpoints()
    } catch {
      // ignore
    }
  }

  const doToggle = async (ep) => {
    try {
      const resp = await fetch(`/api/endpoints/${ep.id}/toggle`, { method: 'PATCH' })
      const json = await resp.json()
      if (json.success) {
        fetchEndpoints()
      }
    } catch {
      // ignore
    }
  }

  const statusColors = {
    green: 'var(--green)',
    yellow: 'var(--yellow)',
    red: 'var(--red)',
    gray: 'var(--gray)',
  }

  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center justify-between mb-2">
        <h2 style={{ margin: 0 }}>Endpoints</h2>
        <button
          onClick={openCreate}
          className="rounded px-2 py-0.5 text-xs font-semibold"
          style={{
            background: 'var(--accent)',
            color: '#fff',
            border: 'none',
            cursor: 'pointer',
          }}
        >
          + Add
        </button>
      </div>

      {endpoints.length === 0 && (
        <p className="text-xs" style={{ color: 'var(--gray)' }}>No endpoints configured.</p>
      )}

      <div className="flex flex-col gap-1">
        {endpoints.map((ep) => (
          <div
            key={ep.id}
            className="flex items-center gap-2 rounded px-2 py-1.5 text-xs"
            style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}
          >
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ backgroundColor: statusColors[ep.status] || 'var(--gray)' }}
            />
            <span style={{ color: 'var(--text-h)', fontWeight: 600, minWidth: '12ch' }}>
              {ep.name}
            </span>
            <span style={{ color: 'var(--accent)', fontFamily: 'var(--mono)', fontSize: 10, flex: 1 }}>
              {ep.target_host}
            </span>
            <span
              className="rounded px-1.5 py-0.5 text-xs font-semibold cursor-pointer select-none"
              onClick={() => doToggle(ep)}
              style={{
                background: ep.enabled ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                color: ep.enabled ? 'var(--green)' : 'var(--red)',
                border: `1px solid ${ep.enabled ? 'var(--green)' : 'var(--red)'}`,
                fontSize: 9,
              }}
            >
              {ep.enabled ? 'ON' : 'OFF'}
            </span>
            <button
              onClick={() => openEdit(ep)}
              className="rounded px-1.5 py-0.5 text-xs"
              style={{
                background: 'transparent',
                border: '1px solid var(--border)',
                color: 'var(--gray)',
                cursor: 'pointer',
              }}
            >
              Edit
            </button>
            <button
              onClick={() => doDelete(ep)}
              className="rounded px-1.5 py-0.5 text-xs"
              style={{
                background: 'transparent',
                border: '1px solid var(--border)',
                color: 'var(--red)',
                cursor: 'pointer',
              }}
            >
              Del
            </button>
          </div>
        ))}
      </div>

      {showForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.6)' }}
        >
          <div
            className="rounded-lg p-4 flex flex-col gap-3"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', minWidth: 320 }}
          >
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-h)' }}>
              {editId ? 'Edit Endpoint' : 'New Endpoint'}
            </h3>

            <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
              Name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Google DNS"
                className="rounded px-2 py-1 text-sm"
                style={{
                  background: 'var(--bg)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-h)',
                  outline: 'none',
                }}
              />
            </label>

            <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
              Target Host (IP or hostname)
              <input
                value={targetHost}
                onChange={(e) => setTargetHost(e.target.value)}
                placeholder="e.g. 8.8.8.8"
                className="rounded px-2 py-1 text-sm"
                style={{
                  background: 'var(--bg)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-h)',
                  outline: 'none',
                }}
              />
            </label>

            {error && (
              <p className="text-xs" style={{ color: 'var(--red)' }}>{error}</p>
            )}

            <div className="flex gap-2 justify-end">
              <button
                onClick={resetForm}
                className="rounded px-3 py-1 text-xs"
                style={{
                  background: 'transparent',
                  border: '1px solid var(--border)',
                  color: 'var(--gray)',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={save}
                disabled={saving || !name.trim() || !targetHost.trim()}
                className="rounded px-3 py-1 text-xs font-semibold"
                style={{
                  background: saving || !name.trim() || !targetHost.trim() ? 'var(--border)' : 'var(--accent)',
                  color: '#fff',
                  border: 'none',
                  cursor: saving || !name.trim() || !targetHost.trim() ? 'not-allowed' : 'pointer',
                }}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
