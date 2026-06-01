import { useState } from 'react'
import useMetricsStore, { EMPTY_ARR } from '../store/metricsStore'

const STATUS_COLORS = {
  green: 'var(--green)',
  yellow: 'var(--yellow)',
  red: 'var(--red)',
  gray: 'var(--gray)',
}

function Sparkline({ values, color }) {
  if (!values || values.length === 0) return null
  const max = Math.max(...values, 1)
  return (
    <div className="flex gap-0.5 items-end h-5">
      {values.slice(-8).map((v, i) => (
        <div
          key={i}
          className="w-1 rounded-t-sm transition-all"
          style={{
            height: `${Math.max(3, (v / max) * 100)}%`,
            backgroundColor: color || 'var(--accent)',
            opacity: 0.7,
          }}
        />
      ))}
    </div>
  )
}

export default function EndpointCard({ endpoint }) {
  const probeMetrics = useMetricsStore((s) => s.probeMetrics)
  const probeHistory = useMetricsStore((s) => s.probeHistory)
  const networkChaos = useMetricsStore((s) => s.networkChaos)
  const fetchEndpoints = useMetricsStore((s) => s.fetchEndpoints)

  const probeId = endpoint.probe_id
  const data = probeMetrics[probeId]
  const history = probeHistory[probeId] || EMPTY_ARR
  const isUnderChaos = networkChaos?.probe_id === probeId
  const statusColor = STATUS_COLORS[endpoint.probe_status] || 'var(--gray)'

  const [showForm, setShowForm] = useState(false)
  const [editName, setEditName] = useState('')
  const [editTarget, setEditTarget] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const openEdit = () => {
    setEditName(endpoint.name)
    setEditTarget(endpoint.target_host)
    setShowForm(true)
    setError('')
  }

  const resetForm = () => {
    setShowForm(false)
    setEditName('')
    setEditTarget('')
    setError('')
  }

  const saveEdit = async () => {
    setSaving(true)
    setError('')
    try {
      const resp = await fetch(`/api/endpoints/${endpoint.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: editName.trim(), target_host: editTarget.trim() }),
      })
      const json = await resp.json()
      if (!json.success) {
        setError(json.detail || json.error?.message || 'Save failed')
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

  const doDelete = async () => {
    if (!window.confirm(`Delete endpoint "${endpoint.name}" (${endpoint.target_host})?`)) return
    try {
      await fetch(`/api/endpoints/${endpoint.id}`, { method: 'DELETE' })
      fetchEndpoints()
    } catch {
      // ignore
    }
  }

  const doToggle = async () => {
    try {
      await fetch(`/api/endpoints/${endpoint.id}/toggle`, { method: 'PATCH' })
      fetchEndpoints()
    } catch {
      // ignore
    }
  }

  const latencyVals = history.map((p) => p.latency_ms)

  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', opacity: endpoint.enabled ? 1 : 0.65 }}
    >
      {/* Header: status dot + name + status badge */}
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: endpoint.enabled ? statusColor : 'var(--gray)' }} />
        <h3 className="truncate" style={{ margin: 0, fontSize: 13, flex: 1, opacity: endpoint.enabled ? 1 : 0.5 }} title={endpoint.name}>
          {endpoint.name}
        </h3>
        <span
          className="rounded px-1.5 py-0.5 text-xs font-semibold"
          style={{
            background: endpoint.enabled ? 'var(--accent-bg)' : 'rgba(239,68,68,0.1)',
            color: endpoint.enabled ? 'var(--accent)' : 'var(--red)',
            fontSize: 10,
            whiteSpace: 'nowrap',
          }}
        >
          {endpoint.enabled ? (endpoint.probe_status || 'gray') : 'OFF'}
        </span>
        {isUnderChaos && (
          <span
            className="rounded px-1.5 py-0.5 text-xs font-semibold"
            style={{
              background: 'rgba(239,68,68,0.15)',
              color: 'var(--red)',
              fontSize: 10,
              border: '1px solid var(--red)',
              whiteSpace: 'nowrap',
            }}
          >
            CHAOS
          </span>
        )}
      </div>

      {/* Target host */}
      <p className="text-xs mb-2 truncate" style={{ color: 'var(--gray)' }}>
        ICMP &rarr; {endpoint.target_host}
      </p>

      {/* Metrics or disabled / gray state */}
      {!endpoint.enabled ? (
        <div className="mb-2 rounded px-2 py-2 text-center" style={{ background: 'var(--bg)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--red)' }}>Monitoring Disabled</p>
        </div>
      ) : !data ? (
        <p className="text-xs mb-2" style={{ color: 'var(--gray)' }}>Waiting for probe data...</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-x-2 gap-y-1 text-xs mb-2">
            <div>
              <span style={{ color: 'var(--gray)' }}>Lat</span>
              <span className="ml-1 font-semibold" style={{ color: 'var(--text-h)' }}>
                {data.latency_ms.toFixed(1)}ms
              </span>
            </div>
            <div>
              <span style={{ color: 'var(--gray)' }}>Loss</span>
              <span className="ml-1 font-semibold" style={{ color: 'var(--text-h)' }}>
                {data.packet_loss_pct.toFixed(1)}%
              </span>
            </div>
            <div>
              <span style={{ color: 'var(--gray)' }}>Avail</span>
              <span className="ml-1 font-semibold" style={{ color: 'var(--text-h)' }}>
                {data.availability_pct.toFixed(1)}%
              </span>
            </div>
          </div>

          {/* Sparkline */}
          <div className="mb-2">
            <p className="text-xs mb-1" style={{ color: 'var(--gray)' }}>Latency trend</p>
            <Sparkline values={latencyVals} color={statusColor} />
          </div>
        </>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1 mt-2 pt-2" style={{ borderTop: '1px solid var(--border)' }}>
        <button
          onClick={doToggle}
          className="rounded px-1.5 py-0.5 text-xs font-semibold"
          style={{
            background: endpoint.enabled ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
            color: endpoint.enabled ? 'var(--green)' : 'var(--red)',
            border: `1px solid ${endpoint.enabled ? 'var(--green)' : 'var(--red)'}`,
            fontSize: 9,
            cursor: 'pointer',
          }}
        >
          {endpoint.enabled ? 'ON' : 'OFF'}
        </button>
        <button
          onClick={openEdit}
          className="rounded px-1.5 py-0.5 text-xs"
          style={{
            background: 'transparent',
            border: '1px solid var(--border)',
            color: 'var(--gray)',
            cursor: 'pointer',
            fontSize: 9,
          }}
        >
          Edit
        </button>
        <button
          onClick={doDelete}
          className="rounded px-1.5 py-0.5 text-xs"
          style={{
            background: 'transparent',
            border: '1px solid var(--border)',
            color: 'var(--red)',
            cursor: 'pointer',
            fontSize: 9,
          }}
        >
          Del
        </button>
        {probeId && (
          <span className="ml-auto text-xs" style={{ color: 'var(--gray)', fontSize: 8, fontFamily: 'var(--mono)' }}>
            {probeId}
          </span>
        )}
      </div>

      {/* Edit Modal */}
      {showForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.6)' }}
        >
          <div
            className="rounded-lg p-4 flex flex-col gap-3"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', minWidth: 320 }}
          >
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-h)' }}>Edit Endpoint</h3>

            <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
              Name
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
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
              Target Host
              <input
                value={editTarget}
                onChange={(e) => setEditTarget(e.target.value)}
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
                onClick={saveEdit}
                disabled={saving || !editName.trim() || !editTarget.trim()}
                className="rounded px-3 py-1 text-xs font-semibold"
                style={{
                  background: saving || !editName.trim() || !editTarget.trim() ? 'var(--border)' : 'var(--accent)',
                  color: '#fff',
                  border: 'none',
                  cursor: saving || !editName.trim() || !editTarget.trim() ? 'not-allowed' : 'pointer',
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
