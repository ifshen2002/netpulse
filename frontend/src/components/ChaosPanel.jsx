import { useState } from 'react'
import useMetricsStore from '../store/metricsStore'

const CHAOS_TYPES = ['latency_spike', 'cpu_spike', 'packet_loss', 'db_exhaustion', 'cache_unavailable']
const CHAOS_LABELS = {
  latency_spike: 'Latency+',
  cpu_spike: 'CPU+',
  packet_loss: 'PktLoss',
  db_exhaustion: 'DB-Exh',
  cache_unavailable: 'Cache-Off',
}
const SYNTH_NODES = ['node-2', 'node-3']

export default function ChaosPanel() {
  const chaosActive = useMetricsStore((s) => s.chaosActive)
  const [injecting, setInjecting] = useState(null)

  async function doInject(nodeId, chaosType) {
    setInjecting(`${nodeId}:${chaosType}`)
    try {
      await fetch('/api/chaos/inject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: nodeId, chaos_type: chaosType }),
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
    setInjecting(null)
  }

  async function doRecover(nodeId) {
    try {
      await fetch('/api/chaos/recover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(nodeId ? { node_id: nodeId } : {}),
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
  }

  function isActive(nodeId, chaosType) {
    return (chaosActive[nodeId] || []).includes(chaosType)
  }

  return (
    <div className="flex flex-col gap-2 h-full text-xs">
      {SYNTH_NODES.map((nid) => (
        <div key={nid} className="flex items-center gap-1 flex-wrap">
          <span className="font-semibold w-14 flex-shrink-0" style={{ color: 'var(--text-h)' }}>{nid}</span>
          {CHAOS_TYPES.map((ct) => {
            const active = isActive(nid, ct)
            const busy = injecting === `${nid}:${ct}`
            return (
              <button
                key={ct}
                disabled={!!injecting}
                onClick={() => active ? doRecover(nid) : doInject(nid, ct)}
                className="rounded px-1.5 py-0.5 border transition-colors"
                style={{
                  background: active ? 'var(--accent-bg)' : 'transparent',
                  borderColor: active ? 'var(--accent)' : 'var(--border)',
                  color: active ? 'var(--accent)' : 'var(--text)',
                  opacity: busy ? 0.5 : 1,
                  cursor: injecting ? 'wait' : 'pointer',
                }}
              >
                {busy ? '...' : CHAOS_LABELS[ct]}
              </button>
            )
          })}
        </div>
      ))}
      <button
        onClick={() => doRecover(null)}
        className="rounded px-2 py-1 mt-1 font-semibold"
        style={{
          background: 'var(--red)',
          color: '#fff',
          border: 'none',
          cursor: 'pointer',
          fontSize: 11,
        }}
      >
        RECOVER ALL
      </button>
    </div>
  )
}
