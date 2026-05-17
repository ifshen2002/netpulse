import useMetricsStore from '../store/metricsStore'
import { toUTC8 } from '../lib/time'

const TYPE_COLORS = {
  cpu_high: 'var(--red)',
  latency_spike: 'var(--yellow)',
  heartbeat_timeout: 'var(--gray)',
  db_exhaustion: 'var(--accent)',
  cache_unavailable: 'var(--accent)',
}

const THRESHOLD_LABELS = {
  cpu_high: '>80%',
  latency_spike: '>500ms',
  heartbeat_timeout: '15s',
  db_exhaustion: 'DB off',
  cache_unavailable: 'Cache off',
}

export default function AlertBanner() {
  const alerts = useMetricsStore((s) => s.alerts)
  const recent = alerts.slice(0, 5)

  if (recent.length === 0) {
    return (
      <div className="flex items-center h-full px-3 text-xs" style={{ color: 'var(--gray)' }}>
        No alerts — system nominal
      </div>
    )
  }

  return (
    <div className="flex gap-2 h-full items-center px-2 overflow-hidden">
      {recent.map((a, i) => (
        <div
          key={`${a.alert_id || i}`}
          className="flex-shrink-0 rounded px-2 py-0.5 text-xs whitespace-nowrap"
          style={{
            background: 'var(--bg-card)',
            borderLeft: `3px solid ${TYPE_COLORS[a.alert_type] || 'var(--gray)'}`,
          }}
        >
          <span className="font-semibold" style={{ color: 'var(--text-h)' }}>[{a.alert_type}]</span>
          <span className="ml-1" style={{ color: 'var(--text)' }}>{a.node_id}</span>
          <span className="ml-1" style={{ color: 'var(--gray)' }}>{a.message}</span>
          <span
            className="ml-1 rounded px-1"
            style={{
              background: 'var(--bg)',
              color: TYPE_COLORS[a.alert_type] || 'var(--gray)',
              fontSize: 10,
              border: `1px solid ${TYPE_COLORS[a.alert_type] || 'var(--border)'}`,
              opacity: 0.85,
            }}
          >
            {THRESHOLD_LABELS[a.alert_type] || a.alert_type}
          </span>
          <span className="ml-1" style={{ color: 'var(--gray)' }}>
            {toUTC8(a.timestamp)}
          </span>
        </div>
      ))}
      {alerts.length > 5 && (
        <span style={{ color: 'var(--gray)', flexShrink: 0 }}>
          +{alerts.length - 5} more
        </span>
      )}
    </div>
  )
}
