import { useRef, useEffect } from 'react'
import useMetricsStore from '../store/metricsStore'

const TYPE_COLORS = {
  cpu_high: 'var(--red)',
  latency_spike: 'var(--yellow)',
  heartbeat_timeout: 'var(--gray)',
  db_exhaustion: 'var(--accent)',
  cache_unavailable: 'var(--accent)',
}

export default function AlertBanner() {
  const alerts = useMetricsStore((s) => s.alerts)
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = 0
    }
  }, [alerts.length])

  if (alerts.length === 0) {
    return (
      <div className="flex items-center h-full px-3 text-xs" style={{ color: 'var(--gray)' }}>
        No alerts — system nominal
      </div>
    )
  }

  return (
    <div ref={scrollRef} className="flex gap-2 overflow-x-auto h-full items-center px-2">
      {alerts.map((a, i) => (
        <div
          key={`${a.alert_id || i}`}
          className="flex-shrink-0 rounded px-2 py-1 text-xs whitespace-nowrap"
          style={{
            background: 'var(--bg-card)',
            borderLeft: `3px solid ${TYPE_COLORS[a.alert_type] || 'var(--gray)'}`,
          }}
        >
          <span className="font-semibold" style={{ color: 'var(--text-h)' }}>[{a.alert_type}]</span>
          <span className="ml-1.5" style={{ color: 'var(--text)' }}>{a.node_id}</span>
          <span className="ml-1.5" style={{ color: 'var(--gray)' }}>{a.message}</span>
          <span className="ml-2" style={{ color: 'var(--gray)' }}>
            {(a.timestamp || '').slice(11, 19)}
          </span>
        </div>
      ))}
    </div>
  )
}
