import useMetricsStore, { EMPTY_ARR } from '../store/metricsStore'

const STATUS_COLORS = {
  green: 'var(--green)',
  yellow: 'var(--yellow)',
  red: 'var(--red)',
  gray: 'var(--gray)',
}

function Sparkline({ values, color }) {
  if (!values || values.length === 0) return null
  const max = Math.max(...values, 1)
  return (
    <div className="flex gap-0.5 items-end h-5">
      {values.slice(-8).map((v, i) => (
        <div
          key={i}
          className="w-1 rounded-t-sm transition-all"
          style={{
            height: `${Math.max(3, (v / max) * 100)}%`,
            backgroundColor: color || 'var(--accent)',
            opacity: 0.7,
          }}
        />
      ))}
    </div>
  )
}

export default function ProbeCard({ probeId }) {
  const data = useMetricsStore((s) => s.probeMetrics[probeId])
  const history = useMetricsStore((s) => s.probeHistory[probeId] || EMPTY_ARR)
  const networkChaos = useMetricsStore((s) => s.networkChaos)
  const isUnderChaos = networkChaos?.probe_id === probeId

  // Derive probe name and endpoint from first data or fall back to probeId
  const endpoint = data?.endpoint || probeId
  const latencyVals = history.map((p) => p.latency_ms)

  if (!data) {
    return (
      <div
        className="rounded-lg p-3"
        style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2 mb-2">
          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: 'var(--gray)' }} />
          <h3 style={{ margin: 0, fontSize: 13 }}>{probeId}</h3>
        </div>
        <p className="text-xs mb-2" style={{ color: 'var(--gray)' }}>
          ICMP &rarr; {endpoint}
        </p>
        <p className="text-xs" style={{ color: 'var(--gray)' }}>No data</p>
      </div>
    )
  }

  const statusColor = STATUS_COLORS[data.status] || 'var(--gray)'

  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: statusColor }} />
        <h3 style={{ margin: 0, fontSize: 13 }}>{probeId}</h3>
        <span
          className="text-xs px-1.5 py-0.5 rounded"
          style={{ background: 'var(--accent-bg)', color: 'var(--accent)', fontSize: 10 }}
        >
          {data.status}
        </span>
        {isUnderChaos && (
          <span
            className="text-xs px-1.5 py-0.5 rounded"
            style={{
              background: 'rgba(239,68,68,0.15)',
              color: 'var(--red)',
              fontSize: 10,
              border: '1px solid var(--red)',
            }}
          >
            CHAOS
          </span>
        )}
      </div>
      <p className="text-xs mb-2" style={{ color: 'var(--gray)' }}>
        ICMP &rarr; {endpoint}
      </p>
      <div className="grid grid-cols-3 gap-x-2 gap-y-1 text-xs mb-2">
        <div>
          <span style={{ color: 'var(--gray)' }}>Lat</span>
          <span className="ml-1 font-semibold" style={{ color: 'var(--text-h)' }}>
            {data.latency_ms.toFixed(1)}ms
          </span>
        </div>
        <div>
          <span style={{ color: 'var(--gray)' }}>Loss</span>
          <span className="ml-1 font-semibold" style={{ color: 'var(--text-h)' }}>
            {data.packet_loss_pct.toFixed(1)}%
          </span>
        </div>
        <div>
          <span style={{ color: 'var(--gray)' }}>Avail</span>
          <span className="ml-1 font-semibold" style={{ color: 'var(--text-h)' }}>
            {data.availability_pct.toFixed(1)}%
          </span>
        </div>
      </div>
      <div>
        <p className="text-xs mb-1" style={{ color: 'var(--gray)' }}>Latency trend</p>
        <Sparkline values={latencyVals} color={statusColor} />
      </div>
    </div>
  )
}
