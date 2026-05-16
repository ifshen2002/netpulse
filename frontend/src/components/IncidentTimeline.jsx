import useMetricsStore from '../store/metricsStore'

export default function IncidentTimeline() {
  const incidents = useMetricsStore((s) => s.incidents)

  if (incidents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-xs" style={{ color: 'var(--gray)' }}>
        No incidents — all clear
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1.5 overflow-y-auto h-full">
      {incidents.map((inc) => (
        <div
          key={inc.incident_id}
          className="flex items-center gap-3 rounded px-3 py-1.5 text-xs"
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            opacity: inc.status === 'closed' ? 0.45 : 1,
          }}
        >
          <span style={{ fontSize: 10 }}>
            {inc.status === 'open' ? '\u{1F534}' : '✅'}
          </span>
          <span className="font-semibold flex-1" style={{ color: 'var(--text-h)' }}>{inc.title}</span>
          <span style={{ color: 'var(--gray)' }}>{inc.node_id}</span>
          <span className="rounded px-1 py-0.5" style={{ background: 'var(--accent-bg)', color: 'var(--accent)', fontSize: 10 }}>
            {inc.alertCount} alert{inc.alertCount !== 1 ? 's' : ''}
          </span>
          <span style={{ color: 'var(--gray)', fontSize: 10 }}>
            {(inc.timestamp || '').slice(11, 19)}
          </span>
        </div>
      ))}
    </div>
  )
}
