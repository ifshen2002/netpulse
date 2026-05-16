import { useState, useEffect, useRef } from 'react'
import useWebSocket from './hooks/useWebSocket'
import useMetricsStore from './store/metricsStore'
import NodeCard from './components/NodeCard'
import MetricsChart from './components/MetricsChart'
import AlertBanner from './components/AlertBanner'
import IncidentTimeline from './components/IncidentTimeline'
import ChaosPanel from './components/ChaosPanel'
import NodeControls from './components/NodeControls'

const NODE_IDS = ['node-1', 'node-2', 'node-3']

export default function App() {
  useWebSocket()
  const connected = useMetricsStore((s) => s.connected)
  const [showDegraded, setShowDegraded] = useState(false)
  const disconnectSince = useRef(null)

  useEffect(() => {
    if (!connected) {
      disconnectSince.current = Date.now()
      const timer = setTimeout(() => setShowDegraded(true), 10000)
      return () => clearTimeout(timer)
    } else {
      disconnectSince.current = null
      setShowDegraded(false)
    }
  }, [connected])

  return (
    <main className="min-h-screen p-3" style={{ background: 'var(--bg)' }}>
      {/* header */}
      <div className="flex items-center justify-between mb-3 px-1">
        <h1 style={{ margin: 0, fontSize: 20, letterSpacing: -0.5 }}>NetPulse NOC</h1>
        <div className="flex items-center gap-2 text-xs">
          <span
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: connected ? 'var(--green)' : 'var(--red)' }}
          />
          <span style={{ color: connected ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
            {connected ? 'LIVE' : 'DISCONNECTED'}
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-3 relative">
        {/* degraded overlay */}
        {showDegraded && (
          <div
            className="absolute inset-0 z-10 flex items-center justify-center rounded-lg"
            style={{ background: 'rgba(15,17,23,0.75)', backdropFilter: 'blur(2px)' }}
          >
            <p className="text-sm font-semibold" style={{ color: 'var(--yellow)' }}>
              Live data paused — reconnecting...
            </p>
          </div>
        )}

        {/* Panel 1: NodeGrid */}
        <div className="grid grid-cols-3 gap-3">
          {NODE_IDS.map((id) => (
            <NodeCard key={id} nodeId={id} />
          ))}
        </div>

        {/* Panel 2: Telemetry (chart + alerts) */}
        <div
          className="rounded-lg p-3 flex flex-col gap-2"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        >
          <h2>Telemetry</h2>
          <div style={{ height: 220 }}>
            <MetricsChart />
          </div>
          <div
            className="rounded mt-1 overflow-hidden"
            style={{ height: 28, background: 'var(--bg)', border: '1px solid var(--border)' }}
          >
            <AlertBanner />
          </div>
        </div>

        {/* Panel 3: IncidentTimeline */}
        <div
          className="rounded-lg p-3"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', maxHeight: 180, overflowY: 'auto' }}
        >
          <h2>Incidents</h2>
          <IncidentTimeline />
        </div>

        {/* Panel 4: ControlBar (chaos + node controls) */}
        <div className="grid grid-cols-2 gap-3">
          <div
            className="rounded-lg p-3"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          >
            <h2>Chaos Injection</h2>
            <ChaosPanel />
          </div>
          <div
            className="rounded-lg p-3"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
          >
            <h2>Burst Mode</h2>
            <NodeControls />
          </div>
        </div>
      </div>
    </main>
  )
}
