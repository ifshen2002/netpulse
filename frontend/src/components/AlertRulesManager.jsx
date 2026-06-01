import { useState, useEffect } from 'react'

const VALID_METRICS = ['latency', 'packet_loss', 'availability']
const VALID_OPERATORS = ['>', '<', '>=', '<=']
const VALID_SEVERITIES = ['warning', 'critical']

const SEVERITY_COLORS = {
  warning: 'var(--yellow)',
  critical: 'var(--red)',
}

const METRIC_LABELS = {
  latency: 'Latency (ms)',
  packet_loss: 'Packet Loss (%)',
  availability: 'Availability (%)',
}

export default function AlertRulesManager() {
  const [rules, setRules] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState({ name: '', metric: 'latency', operator: '>', threshold: 100, severity: 'critical' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    async function load() {
      try {
        const resp = await fetch('/api/alert-rules')
        const json = await resp.json()
        if (json.success) {
          setRules(json.data)
        }
      } catch {
        // backend may not be ready
      }
      setLoaded(true)
    }
    load()
  }, [])

  async function refreshRules() {
    try {
      const resp = await fetch('/api/alert-rules')
      const json = await resp.json()
      if (json.success) {
        setRules(json.data)
      }
    } catch {
      // backend may not be ready
    }
  }

  const resetForm = () => {
    setForm({ name: '', metric: 'latency', operator: '>', threshold: 100, severity: 'critical' })
    setEditId(null)
    setShowForm(false)
    setError('')
  }

  const openCreate = () => {
    resetForm()
    setShowForm(true)
  }

  const openEdit = (rule) => {
    setForm({
      name: rule.name,
      metric: rule.metric,
      operator: rule.operator,
      threshold: rule.threshold,
      severity: rule.severity,
    })
    setEditId(rule.id)
    setShowForm(true)
    setError('')
  }

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const url = editId ? `/api/alert-rules/${editId}` : '/api/alert-rules'
      const method = editId ? 'PUT' : 'POST'
      const resp = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const json = await resp.json()
      if (!json.success) {
        setError(json.error?.message || 'Save failed')
        return
      }
      refreshRules()
      resetForm()
    } catch {
      setError('Network error')
    } finally {
      setSaving(false)
    }
  }

  const doDelete = async (rule) => {
    if (!window.confirm(`Delete rule "${rule.name}"?`)) return
    try {
      await fetch(`/api/alert-rules/${rule.id}`, { method: 'DELETE' })
      refreshRules()
    } catch {
      // ignore
    }
  }

  const doToggle = async (rule) => {
    try {
      await fetch(`/api/alert-rules/${rule.id}/toggle`, { method: 'PATCH' })
      refreshRules()
    } catch {
      // ignore
    }
  }

  if (!loaded) return null

  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center justify-between mb-2">
        <h2 style={{ margin: 0 }}>Alert Rules</h2>
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
          + Add Rule
        </button>
      </div>

      {rules.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--gray)' }}>No alert rules configured.</p>
      ) : (
        <div className="flex flex-col gap-1">
          {rules.map((rule) => (
            <div
              key={rule.id}
              className="flex items-center gap-2 rounded px-2 py-1 text-xs"
              style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: SEVERITY_COLORS[rule.severity] || 'var(--gray)' }}
              />
              <span style={{ color: 'var(--text-h)', fontWeight: 600, minWidth: '14ch', fontSize: 10 }}>
                {rule.name}
              </span>
              <span style={{ color: 'var(--gray)', fontSize: 10, fontFamily: 'var(--mono)' }}>
                {rule.metric} {rule.operator} {rule.threshold}
              </span>
              <span
                className="rounded px-1 py-0.5 text-xs font-semibold"
                style={{
                  background: rule.severity === 'critical' ? 'rgba(239,68,68,0.12)' : 'rgba(234,179,8,0.12)',
                  color: SEVERITY_COLORS[rule.severity],
                  border: `1px solid ${SEVERITY_COLORS[rule.severity]}`,
                  fontSize: 8,
                }}
              >
                {rule.severity.toUpperCase()}
              </span>
              <span
                className="rounded px-1.5 py-0.5 text-xs font-semibold cursor-pointer select-none"
                onClick={() => doToggle(rule)}
                style={{
                  background: rule.enabled ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                  color: rule.enabled ? 'var(--green)' : 'var(--red)',
                  border: `1px solid ${rule.enabled ? 'var(--green)' : 'var(--red)'}`,
                  fontSize: 8,
                  marginLeft: 'auto',
                }}
              >
                {rule.enabled ? 'ON' : 'OFF'}
              </span>
              <button
                onClick={() => openEdit(rule)}
                className="rounded px-1.5 py-0.5 text-xs"
                style={{
                  background: 'transparent',
                  border: '1px solid var(--border)',
                  color: 'var(--gray)',
                  cursor: 'pointer',
                  fontSize: 10,
                }}
              >
                Edit
              </button>
              <button
                onClick={() => doDelete(rule)}
                className="rounded px-1.5 py-0.5 text-xs"
                style={{
                  background: 'transparent',
                  border: '1px solid var(--border)',
                  color: 'var(--red)',
                  cursor: 'pointer',
                  fontSize: 10,
                }}
              >
                Del
              </button>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.6)' }}
        >
          <div
            className="rounded-lg p-4 flex flex-col gap-3"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', minWidth: 340 }}
          >
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-h)' }}>
              {editId ? 'Edit Rule' : 'New Alert Rule'}
            </h3>

            <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
              Name
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Latency Warning"
                className="rounded px-2 py-1 text-sm"
                style={{
                  background: 'var(--bg)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-h)',
                  outline: 'none',
                }}
              />
            </label>

            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
                Metric
                <select
                  value={form.metric}
                  onChange={(e) => setForm({ ...form, metric: e.target.value })}
                  className="rounded px-2 py-1 text-sm"
                  style={{
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-h)',
                    outline: 'none',
                  }}
                >
                  {VALID_METRICS.map((m) => (
                    <option key={m} value={m}>{METRIC_LABELS[m]}</option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
                Severity
                <select
                  value={form.severity}
                  onChange={(e) => setForm({ ...form, severity: e.target.value })}
                  className="rounded px-2 py-1 text-sm"
                  style={{
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-h)',
                    outline: 'none',
                  }}
                >
                  {VALID_SEVERITIES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </label>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
                Operator
                <select
                  value={form.operator}
                  onChange={(e) => setForm({ ...form, operator: e.target.value })}
                  className="rounded px-2 py-1 text-sm"
                  style={{
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-h)',
                    outline: 'none',
                  }}
                >
                  {VALID_OPERATORS.map((op) => (
                    <option key={op} value={op}>{op}</option>
                  ))}
                </select>
              </label>

              <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
                Threshold
                <input
                  type="number"
                  value={form.threshold}
                  onChange={(e) => setForm({ ...form, threshold: Number(e.target.value) })}
                  className="rounded px-2 py-1 text-sm"
                  style={{
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-h)',
                    outline: 'none',
                  }}
                />
              </label>
            </div>

            {error && (
              <p className="text-xs" style={{ color: 'var(--red)' }}>{error}</p>
            )}

            <div className="flex gap-2 justify-end mt-1">
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
                disabled={saving || !form.name.trim()}
                className="rounded px-3 py-1 text-xs font-semibold"
                style={{
                  background: saving || !form.name.trim() ? 'var(--border)' : 'var(--accent)',
                  color: '#fff',
                  border: 'none',
                  cursor: saving || !form.name.trim() ? 'not-allowed' : 'pointer',
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
