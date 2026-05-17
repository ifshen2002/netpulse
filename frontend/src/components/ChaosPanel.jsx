import { useState } from 'react'
import useMetricsStore from '../store/metricsStore'

const CHAOS_TYPES = ['latency_spike', 'cpu_spike', 'packet_loss', 'db_exhaustion', 'cache_unavailable']
const CHAOS_LABELS = {
  latency_spike: 'Latency',
  cpu_spike: 'CPU',
  packet_loss: 'PktLoss',
  db_exhaustion: 'DB-Exh',
  cache_unavailable: 'Cache-Off',
}
const INTENSITIES = ['low', 'medium', 'high', 'critical']
const INTENSITY_LABELS = { low: 'LOW', medium: 'MED', high: 'HIGH', critical: 'CRIT' }
const OVERLAY_TYPES = new Set(['latency_spike', 'cpu_spike', 'packet_loss'])
const SYNTH_NODES = ['node-2', 'node-3']

export default function ChaosPanel() {
  const chaosActive = useMetricsStore((s) => s.chaosActive)
  const [intensity, setIntensity] = useState('high')
  const [injecting, setInjecting] = useState(null)

  async function doInject(nodeId, chaosType) {
    setInjecting(`${nodeId}:${chaosType}`)
    try {
      await fetch('/api/chaos/inject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_id: nodeId,
          chaos_type: chaosType,
          config: OVERLAY_TYPES.has(chaosType) ? { intensity } : {},
        }),
      })
      const resp = await fetch('/api/chaos/status')
      const json = await resp.json()
      if (json.success) {
        const s = useMetricsStore.getState()
        s.setChaosState(json.data.active || {}, json.data.burst || {})
        if (OVERLAY_TYPES.has(chaosType)) {
          s.incrementChaosCount()
        }
      }
    } catch {
      // ignore
    }
    setInjecting(null)
  }

  async function doRecover(nodeId, chaosType) {
    setInjecting(`${nodeId}:${chaosType || 'all'}`)
    try {
      await fetch('/api/chaos/recover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(
          chaosType ? { node_id: nodeId, chaos_type: chaosType } : {}
        ),
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

  function activeIntensity(nodeId, chaosType) {
    const node = chaosActive[nodeId]
    if (!node) return null
    return node[chaosType] || null
  }

  return (
    <div className="flex flex-col gap-2 h-full text-xs">
      {/* intensity selector */}
      <div className="flex items-center gap-1">
        <span style={{ color: 'var(--gray)', fontSize: 10, minWidth: 48 }}>Intensity</span>
        {INTENSITIES.map((iv) => (
          <button
            key={iv}
            onClick={() => setIntensity(iv)}
            className="rounded px-1.5 py-0.5 border transition-colors"
            style={{
              background: intensity === iv ? 'var(--accent-bg)' : 'transparent',
              borderColor: intensity === iv ? 'var(--accent)' : 'var(--border)',
              color: intensity === iv ? 'var(--accent)' : 'var(--gray)',
              cursor: 'pointer',
              fontSize: 10,
            }}
          >
            {INTENSITY_LABELS[iv]}
          </button>
        ))}
      </div>

      {/* chaos injection per node */}
      {SYNTH_NODES.map((nid) => (
        <div key={nid} className="flex items-center gap-1 flex-wrap">
          <span className="font-semibold w-14 flex-shrink-0" style={{ color: 'var(--text-h)' }}>{nid}</span>
          {CHAOS_TYPES.map((ct) => {
            const current = activeIntensity(nid, ct)
            const busy = injecting === `${nid}:${ct}`
            return (
              <button
                key={ct}
                disabled={!!injecting}
                onClick={() => current ? doRecover(nid, ct) : doInject(nid, ct)}
                className="rounded px-1.5 py-0.5 border transition-colors"
                style={{
                  background: current ? 'var(--accent-bg)' : 'transparent',
                  borderColor: current ? 'var(--accent)' : 'var(--border)',
                  color: current ? 'var(--accent)' : 'var(--text)',
                  opacity: busy ? 0.5 : 1,
                  cursor: injecting ? 'wait' : 'pointer',
                  fontSize: 10,
                }}
                title={
                  current
                    ? `${CHAOS_LABELS[ct]} ${INTENSITY_LABELS[current]} — click to recover`
                    : `${CHAOS_LABELS[ct]} at ${INTENSITY_LABELS[intensity]}`
                }
              >
                {busy ? '...' : current ? `${CHAOS_LABELS[ct]} ${INTENSITY_LABELS[current]}` : CHAOS_LABELS[ct]}
              </button>
            )
          })}
        </div>
      ))}

      <button
        onClick={() => doRecover(null, null)}
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
