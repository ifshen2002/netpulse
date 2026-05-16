import { useState } from 'react'
import useMetricsStore from '../store/metricsStore'

const SYNTH_NODES = ['node-2', 'node-3']

export default function NodeControls() {
  const burstNodes = useMetricsStore((s) => s.burstNodes)
  const [toggling, setToggling] = useState(null)

  async function toggleBurst(nodeId) {
    const current = burstNodes[nodeId] || false
    setToggling(nodeId)
    try {
      await fetch('/api/chaos/burst', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: nodeId, chaos_type: 'burst', config: { enabled: !current } }),
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
    setToggling(null)
  }

  return (
    <div className="flex flex-col gap-2 h-full text-xs">
      <h3>Node Controls</h3>
      {SYNTH_NODES.map((nid) => {
        const burst = burstNodes[nid] || false
        const busy = toggling === nid
        return (
          <div key={nid} className="flex items-center gap-2">
            <span className="font-semibold w-14" style={{ color: 'var(--text-h)' }}>{nid}</span>
            <button
              onClick={() => toggleBurst(nid)}
              disabled={busy}
              className="rounded px-2 py-0.5 border text-xs transition-colors"
              style={{
                background: burst ? 'var(--accent-bg)' : 'transparent',
                borderColor: burst ? 'var(--accent)' : 'var(--border)',
                color: burst ? 'var(--accent)' : 'var(--text)',
                cursor: busy ? 'wait' : 'pointer',
              }}
            >
              {busy ? '...' : burst ? 'BURST ON' : 'BURST OFF'}
            </button>
            <span className="text-xs" style={{ color: 'var(--gray)' }}>
              {burst ? '1s' : '5s'}
            </span>
          </div>
        )
      })}
    </div>
  )
}
