import { useState, useEffect } from 'react'
import useMetricsStore from '../store/metricsStore'

const THRESHOLD_DEFAULTS = {
  latency_ms: 300,
  packet_loss_pct: 5,
  availability_pct: 95,
}

export default function ThresholdConfig() {
  const [thresholds, setThresholds] = useState(THRESHOLD_DEFAULTS)
  const [saving, setSaving] = useState(false)
  const [loaded, setLoaded] = useState(false)

  // Fetch current thresholds on mount
  useEffect(() => {
    async function fetch() {
      try {
        const resp = await fetch('/api/config/alert-thresholds')
        const json = await resp.json()
        if (json.success) {
          setThresholds(json.data)
        }
      } catch {
        // use defaults
      }
      setLoaded(true)
    }
    fetch()
  }, [])

  async function save(field, value) {
    setSaving(true)
    const next = { ...thresholds, [field]: Number(value) }
    setThresholds(next)
    try {
      await fetch('/api/config/alert-thresholds', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: Number(value) }),
      })
    } catch {
      // revert on failure
      setThresholds(thresholds)
    }
    setSaving(false)
  }

  if (!loaded) return null

  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
    >
      <h2>Alert Thresholds</h2>

      <div className="flex flex-col gap-1.5 text-xs">
        {/* Latency */}
        <div className="flex items-center gap-1.5">
          <span style={{ color: 'var(--gray)', minWidth: 80, fontSize: 10 }}>Latency &gt;</span>
          <input
            type="number"
            value={thresholds.latency_ms}
            min={10}
            max={2000}
            onChange={(e) => setThresholds({ ...thresholds, latency_ms: Number(e.target.value) })}
            onBlur={(e) => {
              const v = Math.max(10, Math.min(2000, Number(e.target.value) || 300))
              if (v !== thresholds.latency_ms) save('latency_ms', v)
            }}
            className="rounded px-1.5 py-0.5"
            style={{
              background: 'var(--bg)',
              color: 'var(--text)',
              border: '1px solid var(--border)',
              fontSize: 11,
              width: 52,
            }}
          />
          <span style={{ color: 'var(--gray)', fontSize: 10 }}>ms</span>
        </div>

        {/* Packet Loss */}
        <div className="flex items-center gap-1.5">
          <span style={{ color: 'var(--gray)', minWidth: 80, fontSize: 10 }}>Loss &gt;=</span>
          <input
            type="number"
            value={thresholds.packet_loss_pct}
            min={0.1}
            max={100}
            step={0.5}
            onChange={(e) => setThresholds({ ...thresholds, packet_loss_pct: Number(e.target.value) })}
            onBlur={(e) => {
              const v = Math.max(0.1, Math.min(100, Number(e.target.value) || 5))
              if (v !== thresholds.packet_loss_pct) save('packet_loss_pct', v)
            }}
            className="rounded px-1.5 py-0.5"
            style={{
              background: 'var(--bg)',
              color: 'var(--text)',
              border: '1px solid var(--border)',
              fontSize: 11,
              width: 52,
            }}
          />
          <span style={{ color: 'var(--gray)', fontSize: 10 }}>%</span>
        </div>

        {/* Availability */}
        <div className="flex items-center gap-1.5">
          <span style={{ color: 'var(--gray)', minWidth: 80, fontSize: 10 }}>Avail &lt;=</span>
          <input
            type="number"
            value={thresholds.availability_pct}
            min={0}
            max={100}
            step={0.5}
            onChange={(e) => setThresholds({ ...thresholds, availability_pct: Number(e.target.value) })}
            onBlur={(e) => {
              const v = Math.max(0, Math.min(100, Number(e.target.value) || 95))
              if (v !== thresholds.availability_pct) save('availability_pct', v)
            }}
            className="rounded px-1.5 py-0.5"
            style={{
              background: 'var(--bg)',
              color: 'var(--text)',
              border: '1px solid var(--border)',
              fontSize: 11,
              width: 52,
            }}
          />
          <span style={{ color: 'var(--gray)', fontSize: 10 }}>%</span>
        </div>

        {saving && (
          <span style={{ color: 'var(--accent)', fontSize: 10 }}>Saving...</span>
        )}
      </div>
    </div>
  )
}
