import { useState } from 'react'
import useMetricsStore from '../store/metricsStore'

const CHAOS_TYPES = [
  { key: 'latency', label: 'Latency', unit: 'ms', default: 100, min: 10, max: 500 },
  { key: 'packet_loss', label: 'Packet Loss', unit: '%', default: 10, min: 1, max: 50 },
]

export default function NetworkChaosPanel() {
  const visibleProbes = useMetricsStore((s) => s.visibleProbes)
  const networkChaos = useMetricsStore((s) => s.networkChaos)
  const lastChaosSession = useMetricsStore((s) => s.lastChaosSession)
  const alerts = useMetricsStore((s) => s.alerts)
  const probeIds = Object.keys(visibleProbes).sort()

  const [targetProbe, setTargetProbe] = useState(probeIds[0] || '')
  const [chaosType, setChaosType] = useState('latency')
  const [value, setValue] = useState(100)
  const [injecting, setInjecting] = useState(false)

  const activeType = CHAOS_TYPES.find((t) => t.key === chaosType) || CHAOS_TYPES[0]

  // Keep target in sync when probes load
  if (probeIds.length > 0 && !probeIds.includes(targetProbe)) {
    setTargetProbe(probeIds[0])
  }

  async function doInject() {
    if (!targetProbe) return
    setInjecting(true)
    try {
      await fetch('/api/chaos/network/inject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          probe_id: targetProbe,
          chaos_type: chaosType,
          value: Number(value),
        }),
      })
      // Refresh state
      const resp = await fetch('/api/chaos/network/status')
      const json = await resp.json()
      if (json.success) {
        useMetricsStore.getState().setNetworkChaos(json.data)
      }
    } catch {
      // ignore
    }
    setInjecting(false)
  }

  async function doRecover(probeId) {
    setInjecting(true)
    try {
      const recResp = await fetch('/api/chaos/network/recover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(probeId ? { probe_id: probeId } : {}),
      })
      const recJson = await recResp.json()
      // Capture completed session (includes ended_at) before clearing
      if (recJson.success && recJson.data) {
        useMetricsStore.getState().setNetworkChaos(null)
        // Patch ended_at into lastChaosSession if missing
        const session = { ...recJson.data, ended_at: recJson.data.ended_at || new Date().toISOString() }
        useMetricsStore.setState({ lastChaosSession: session, networkChaos: null })
      } else {
        const resp = await fetch('/api/chaos/network/status')
        const json = await resp.json()
        if (json.success) {
          useMetricsStore.getState().setNetworkChaos(json.data)
        }
      }
    } catch {
      // ignore
    }
    setInjecting(false)
  }

  if (probeIds.length === 0) {
    return (
      <div
        className="rounded-lg p-3"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
      >
        <h2>Network Chaos</h2>
        <p className="text-xs" style={{ color: 'var(--gray)' }}>No probes available</p>
      </div>
    )
  }

  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
    >
      <h2>Network Chaos</h2>

      <div className="flex flex-col gap-2 text-xs">
        {/* Inject controls */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <select
            value={targetProbe}
            onChange={(e) => setTargetProbe(e.target.value)}
            className="rounded px-1.5 py-0.5"
            style={{
              background: 'var(--bg)',
              color: 'var(--text)',
              border: '1px solid var(--border)',
              fontSize: 11,
              cursor: 'pointer',
            }}
          >
            {probeIds.map((pid) => (
              <option key={pid} value={pid}>{pid}</option>
            ))}
          </select>

          <select
            value={chaosType}
            onChange={(e) => {
              const ct = e.target.value
              setChaosType(ct)
              const t = CHAOS_TYPES.find((x) => x.key === ct)
              if (t) setValue(t.default)
            }}
            className="rounded px-1.5 py-0.5"
            style={{
              background: 'var(--bg)',
              color: 'var(--text)',
              border: '1px solid var(--border)',
              fontSize: 11,
              cursor: 'pointer',
            }}
          >
            {CHAOS_TYPES.map((t) => (
              <option key={t.key} value={t.key}>{t.label}</option>
            ))}
          </select>

          <input
            type="number"
            value={value}
            min={activeType.min}
            max={activeType.max}
            onChange={(e) => setValue(e.target.value)}
            className="rounded px-1.5 py-0.5"
            style={{
              background: 'var(--bg)',
              color: 'var(--text)',
              border: '1px solid var(--border)',
              fontSize: 11,
              width: 56,
            }}
          />
          <span style={{ color: 'var(--gray)', fontSize: 10 }}>{activeType.unit}</span>
          <span style={{ color: 'var(--gray)', fontSize: 10 }}>
            ({activeType.min}–{activeType.max})
          </span>

          <button
            onClick={doInject}
            disabled={injecting || !targetProbe}
            className="rounded px-2 py-0.5 font-semibold transition-colors"
            style={{
              background: injecting ? 'var(--gray)' : 'var(--accent-bg)',
              border: `1px solid ${injecting ? 'var(--gray)' : 'var(--accent)'}`,
              color: injecting ? 'var(--bg)' : 'var(--accent)',
              cursor: injecting ? 'wait' : 'pointer',
              fontSize: 11,
            }}
          >
            {injecting ? '...' : 'Inject'}
          </button>
        </div>

        {/* Active chaos */}
        {networkChaos ? (
          <div
            className="flex items-center gap-2 rounded px-2 py-1.5 mt-1"
            style={{ background: 'var(--bg)', border: '1px solid var(--accent)' }}
          >
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: 'var(--accent)' }} />
            <span style={{ color: 'var(--text-h)', fontWeight: 600 }}>
              {networkChaos.probe_id}
            </span>
            <span style={{ color: 'var(--text)' }}>
              {networkChaos.chaos_type} {networkChaos.value}
              {networkChaos.chaos_type === 'latency' ? 'ms' : '%'}
            </span>
            <button
              onClick={() => doRecover(networkChaos.probe_id)}
              disabled={injecting}
              className="rounded px-2 py-0.5 font-semibold ml-auto"
              style={{
                background: 'var(--red)',
                color: '#fff',
                border: 'none',
                cursor: injecting ? 'wait' : 'pointer',
                fontSize: 10,
              }}
            >
              Recover
            </button>
          </div>
        ) : (
          <p className="text-xs" style={{ color: 'var(--gray)' }}>No active chaos</p>
        )}

        {/* Recover All */}
        <button
          onClick={() => doRecover(null)}
          disabled={injecting || !networkChaos}
          className="rounded px-2 py-1 font-semibold mt-1"
          style={{
            background: 'var(--red)',
            color: '#fff',
            border: 'none',
            cursor: injecting || !networkChaos ? 'not-allowed' : 'pointer',
            fontSize: 10,
            opacity: networkChaos ? 1 : 0.4,
          }}
        >
          RECOVER ALL
        </button>

        {/* Last chaos session summary */}
        {lastChaosSession && !networkChaos && (() => {
          const session = lastChaosSession
          // Find alert(s) generated during this session
          const sessionStart = session.started_at
          const sessionEnd = session.ended_at
          const sessionAlerts = alerts.filter((a) =>
            a.probe_id === session.probe_id &&
            a.timestamp >= sessionStart &&
            (!sessionEnd || a.timestamp <= sessionEnd)
          )

          return (
            <div
              className="rounded px-2.5 py-2 mt-1"
              style={{
                background: 'var(--bg)',
                border: '1px solid var(--border)',
              }}
            >
              <p className="text-xs font-semibold mb-1.5" style={{ color: 'var(--text-h)' }}>
                Last Chaos Session
              </p>
              <div className="flex flex-col gap-0.5 text-xs">
                <div className="flex gap-2">
                  <span style={{ color: 'var(--gray)', minWidth: 44 }}>Target:</span>
                  <span style={{ color: 'var(--text-h)', fontWeight: 600 }}>{session.probe_id}</span>
                </div>
                <div className="flex gap-2">
                  <span style={{ color: 'var(--gray)', minWidth: 44 }}>Type:</span>
                  <span style={{ color: 'var(--text)' }}>
                    {session.chaos_type === 'latency' ? 'Latency' : 'Packet Loss'}
                  </span>
                </div>
                <div className="flex gap-2">
                  <span style={{ color: 'var(--gray)', minWidth: 44 }}>Value:</span>
                  <span style={{ color: 'var(--red)', fontWeight: 600 }}>
                    +{session.value}{session.chaos_type === 'latency' ? 'ms' : '%'}
                  </span>
                </div>
                <div className="flex gap-2">
                  <span style={{ color: 'var(--gray)', minWidth: 44 }}>Start:</span>
                  <span style={{ color: 'var(--text)', fontSize: 10 }}>
                    {new Date(session.started_at).toLocaleTimeString()}
                  </span>
                </div>
                {session.ended_at && (
                  <div className="flex gap-2">
                    <span style={{ color: 'var(--gray)', minWidth: 44 }}>End:</span>
                    <span style={{ color: 'var(--text)', fontSize: 10 }}>
                      {new Date(session.ended_at).toLocaleTimeString()}
                    </span>
                  </div>
                )}
                {sessionAlerts.length > 0 && (
                  <div className="flex gap-2 mt-1 pt-1" style={{ borderTop: '1px solid var(--border)' }}>
                    <span style={{ color: 'var(--gray)', minWidth: 44 }}>Alert:</span>
                    <span style={{ color: 'var(--red)', fontWeight: 600 }}>
                      {sessionAlerts[0].alert_type}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )
        })()}
      </div>
    </div>
  )
}
