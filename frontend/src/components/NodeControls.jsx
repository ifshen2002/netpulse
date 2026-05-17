import { useState } from 'react'
import useMetricsStore from '../store/metricsStore'

const SYNTH_NODES = ['node-2', 'node-3']
const INTERVALS = [1, 5, 15, 60]
const INTERVAL_LABELS = { 1: '1s', 5: '5s', 15: '15s', 60: '60s' }

export default function NodeControls() {
  const burstNodes = useMetricsStore((s) => s.burstNodes)
  const [setting, setSetting] = useState(null)

  async function setBurstInterval(nodeId, interval) {
    setSetting(`${nodeId}:${interval}`)
    try {
      await fetch('/api/chaos/burst', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: nodeId, chaos_type: 'burst', config: { interval } }),
      })
      const resp = await fetch('/api/chaos/status')
      const json = await resp.json()
      if (json.success) {
        useMetricsStore.getState().setChaosState(
          json.data.active || {},
          json.data.burst || {}
        )
      }
    } catch {
      // ignore
    }
    setSetting(null)
  }

  return (
    <div className="flex flex-col gap-2 h-full text-xs">
      {SYNTH_NODES.map((nid) => {
        const interval = burstNodes[nid] || 0
        return (
          <div key={nid} className="flex items-center gap-1 flex-wrap">
            <span className="font-semibold w-14 flex-shrink-0" style={{ color: 'var(--text-h)' }}>{nid}</span>
            {INTERVALS.map((iv) => {
              const active = interval === iv
              const busy = setting === `${nid}:${iv}`
              return (
                <button
                  key={iv}
                  disabled={!!setting}
                  onClick={() => setBurstInterval(nid, active ? 0 : iv)}
                  className="rounded px-1.5 py-0.5 border transition-colors"
                  style={{
                    background: active ? 'var(--accent-bg)' : 'transparent',
                    borderColor: active ? 'var(--accent)' : 'var(--border)',
                    color: active ? 'var(--accent)' : 'var(--text)',
                    opacity: busy ? 0.5 : 1,
                    cursor: setting ? 'wait' : 'pointer',
                  }}
                >
                  {busy ? '...' : INTERVAL_LABELS[iv]}
                </button>
              )
            })}
            <span className="text-xs" style={{ color: 'var(--gray)', minWidth: 28 }}>
              {interval > 0 ? `${interval}s` : 'off'}
            </span>
          </div>
        )
      })}
    </div>
  )
}
