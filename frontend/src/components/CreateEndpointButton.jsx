import { useState } from 'react'
import useMetricsStore from '../store/metricsStore'

export default function CreateEndpointButton() {
  const fetchEndpoints = useMetricsStore((s) => s.fetchEndpoints)
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [targetHost, setTargetHost] = useState('')
  const [sourceIp, setSourceIp] = useState('')
  const [sourceIps, setSourceIps] = useState([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const fetchSourceIps = async () => {
    try {
      const resp = await fetch('/api/source-ips')
      const json = await resp.json()
      if (json.success) setSourceIps(json.data || [])
    } catch { /* ignore */ }
  }

  const resetForm = () => {
    setName('')
    setTargetHost('')
    setSourceIp('')
    setShowForm(false)
    setError('')
  }

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      const resp = await fetch('/api/endpoints', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), target_host: targetHost.trim(), source_ip: sourceIp.trim() || null }),
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

  return (
    <>
      <div
        className="rounded-lg p-3 flex items-center justify-center cursor-pointer"
        style={{
          background: 'var(--bg-card)',
          border: '2px dashed var(--border)',
          minHeight: 120,
        }}
        onClick={() => { resetForm(); fetchSourceIps(); setShowForm(true); }}
      >
        <span className="text-sm font-semibold" style={{ color: 'var(--gray)' }}>
          + Add Endpoint
        </span>
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
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-h)' }}>New Endpoint</h3>

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

            {sourceIps.length > 0 && (
              <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
                Source IP (monitoring origin)
                <select
                  value={sourceIp}
                  onChange={(e) => setSourceIp(e.target.value)}
                  className="rounded px-2 py-1 text-sm"
                  style={{
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-h)',
                    outline: 'none',
                  }}
                >
                  <option value="">Auto-detect</option>
                  {sourceIps.map((ip) => (
                    <option key={ip} value={ip}>{ip}</option>
                  ))}
                </select>
              </label>
            )}

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
                {saving ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
