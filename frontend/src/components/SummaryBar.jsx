import useMetricsStore from '../store/metricsStore'

function StatBox({ label, value, color }) {
  return (
    <div
      className="rounded px-3 py-1.5 flex flex-col items-center"
      style={{ background: 'var(--bg)', border: '1px solid var(--border)', minWidth: 100 }}
    >
      <span className="text-xs" style={{ color: 'var(--gray)', fontSize: 9 }}>{label}</span>
      <span className="text-sm font-bold" style={{ color: color || 'var(--text-h)', fontSize: 14 }}>
        {value}
      </span>
    </div>
  )
}

export default function SummaryBar() {
  const endpoints = useMetricsStore((s) => s.endpoints)
  const alerts = useMetricsStore((s) => s.alerts)
  const incidents = useMetricsStore((s) => s.incidents)
  const probeMetrics = useMetricsStore((s) => s.probeMetrics)

  const totalEndpoints = endpoints.length

  const activeAlerts = alerts.filter((a) => !a.resolved_at).length

  const openIncidents = incidents.filter((i) => i.status === 'open').length

  // Average latency across all probes
  const latencies = Object.values(probeMetrics)
    .map((m) => m.latency_ms)
    .filter((v) => v != null && v > 0)
  const avgLatency = latencies.length > 0
    ? (latencies.reduce((a, b) => a + b, 0) / latencies.length).toFixed(1) + 'ms'
    : '—'

  // Average availability across all probes
  const availabilities = Object.values(probeMetrics)
    .map((m) => m.availability_pct)
    .filter((v) => v != null)
  const avgAvailability = availabilities.length > 0
    ? (availabilities.reduce((a, b) => a + b, 0) / availabilities.length).toFixed(1) + '%'
    : '—'

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <StatBox
        label="Endpoints"
        value={totalEndpoints}
        color="var(--accent)"
      />
      <StatBox
        label="Active Alerts"
        value={activeAlerts}
        color={activeAlerts > 0 ? 'var(--red)' : 'var(--green)'}
      />
      <StatBox
        label="Open Incidents"
        value={openIncidents}
        color={openIncidents > 0 ? 'var(--red)' : 'var(--green)'}
      />
      <StatBox
        label="Avg Latency"
        value={avgLatency}
        color="var(--text-h)"
      />
      <StatBox
        label="Availability"
        value={avgAvailability}
        color="var(--green)"
      />
    </div>
  )
}
