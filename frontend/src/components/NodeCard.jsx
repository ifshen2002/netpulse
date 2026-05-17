import { useState } from 'react'
import useMetricsStore, { EMPTY_ARR } from '../store/metricsStore'

const STATUS_COLORS = {
  green: 'var(--green)',
  yellow: 'var(--yellow)',
  red: 'var(--red)',
  gray: 'var(--gray)',
}

const NODE_LABELS = {
  'node-1': 'Host (psutil)',
  'node-2': 'Cloud Service A',
  'node-3': 'Cloud Service B',
}

const STRESS_INTENSITIES = ['low', 'medium', 'high', 'critical']

function Sparkline({ values }) {
  if (!values || values.length === 0) return null
  const max = Math.max(...values, 1)
  return (
    <div className="flex gap-0.5 items-end h-6">
      {values.slice(-5).map((v, i) => (
        <div
          key={i}
          className="w-1.5 rounded-t-sm transition-all"
          style={{
            height: `${Math.max(4, (v / max) * 100)}%`,
            backgroundColor: v > 80 ? 'var(--red)' : v > 60 ? 'var(--yellow)' : 'var(--green)',
            opacity: 0.8,
          }}
        />
      ))}
    </div>
  )
}

function StressTrigger({ nodeId }) {
  const [intensity, setIntensity] = useState('high')
  const [fired, setFired] = useState(false)
  const incrementStress = useMetricsStore((s) => s.incrementStressCount)

  if (nodeId === 'node-1') return null

  const handleFire = () => {
    setFired(true)
    incrementStress()
    setTimeout(() => setFired(false), 1500)
  }

  return (
    <div className="mt-3 pt-2 flex items-center gap-1.5" style={{ borderTop: '1px solid var(--border)' }}>
      <select
        value={intensity}
        onChange={(e) => setIntensity(e.target.value)}
        className="text-xs rounded px-1 py-0.5"
        style={{
          background: 'var(--bg)',
          color: 'var(--text)',
          border: '1px solid var(--border)',
          fontSize: 10,
        }}
      >
        {STRESS_INTENSITIES.map((v) => (
          <option key={v} value={v}>{v}</option>
        ))}
      </select>
      <button
        onClick={handleFire}
        className="rounded px-2 py-0.5 text-xs font-semibold transition-colors"
        style={{
          background: fired ? 'var(--red)' : 'var(--accent-bg)',
          border: `1px solid ${fired ? 'var(--red)' : 'var(--accent)'}`,
          color: fired ? '#fff' : 'var(--accent)',
          cursor: 'pointer',
          fontSize: 10,
        }}
      >
        {fired ? 'Fired!' : 'Stress'}
      </button>
    </div>
  )
}

export default function NodeCard({ nodeId }) {
  const data = useMetricsStore((s) => s.metrics[nodeId])
  const history = useMetricsStore((s) => s.history[nodeId] || EMPTY_ARR)

  if (!data) {
    return (
      <div className="rounded-lg p-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <div className="flex items-center gap-2 mb-3">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: 'var(--gray)' }} />
          <h3 style={{ margin: 0 }}>{nodeId}</h3>
        </div>
        <p className="text-xs" style={{ color: 'var(--gray)' }}>{NODE_LABELS[nodeId]}</p>
        <p className="text-xs mt-2" style={{ color: 'var(--gray)' }}>No data</p>
        <StressTrigger nodeId={nodeId} />
      </div>
    )
  }

  const statusColor = STATUS_COLORS[data.status] || 'var(--gray)'
  const cpuVals = history.map((p) => p.cpu)

  return (
    <div className="rounded-lg p-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
      <div className="flex items-center gap-2 mb-2">
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: statusColor }} />
        <h3 style={{ margin: 0 }}>{nodeId}</h3>
        <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'var(--accent-bg)', color: 'var(--accent)' }}>
          {data.status}
        </span>
      </div>
      <p className="text-xs mb-3" style={{ color: 'var(--gray)' }}>{NODE_LABELS[nodeId]}</p>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <span style={{ color: 'var(--gray)' }}>CPU</span>
          <span className="ml-1 font-semibold" style={{ color: 'var(--text-h)' }}>{data.cpu.toFixed(1)}%</span>
        </div>
        <div>
          <span style={{ color: 'var(--gray)' }}>MEM</span>
          <span className="ml-1 font-semibold" style={{ color: 'var(--text-h)' }}>{data.memory.toFixed(1)}%</span>
        </div>
        <div>
          <span style={{ color: 'var(--gray)' }}>DISK</span>
          <span className="ml-1 font-semibold" style={{ color: 'var(--text-h)' }}>{data.disk.toFixed(1)}%</span>
        </div>
        <div>
          <span style={{ color: 'var(--gray)' }}>LAT</span>
          <span className="ml-1 font-semibold" style={{ color: 'var(--text-h)' }}>{data.latency_ms.toFixed(0)}ms</span>
        </div>
      </div>
      <div className="mt-3">
        <p className="text-xs mb-1" style={{ color: 'var(--gray)' }}>CPU trend</p>
        <Sparkline values={cpuVals} />
      </div>
      <StressTrigger nodeId={nodeId} />
    </div>
  )
}
