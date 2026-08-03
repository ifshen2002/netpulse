import { useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import useMetricsStore, { EMPTY_ARR } from '../store/metricsStore'
import { toUTC8 } from '../lib/time'

const METRICS = [
  { key: 'latency_ms', label: 'Latency', unit: 'ms', yLabel: 'ms' },
  { key: 'packet_loss_pct', label: 'Packet Loss', unit: '%', yLabel: '%' },
  { key: 'availability_pct', label: 'Availability', unit: '%', yLabel: '%' },
]

const ENDPOINT_COLORS = ['var(--accent)', 'var(--green)', 'var(--yellow)', 'var(--red)', '#60a5fa', '#f472b6']

const TIME_OPTIONS = [
  { label: 'ALL', value: 0 },
  { label: '1m', value: 1 },
  { label: '5m', value: 5 },
  { label: '15m', value: 15 },
  { label: '1h', value: 60 },
]

function mergeSeries(probeIds, windowMinutes, history, metricKey) {
  const cutoff = windowMinutes > 0
    ? new Date(Date.now() - windowMinutes * 60 * 1000).toISOString()
    : null

  const allTimestamps = new Set()
  probeIds.forEach((id) => {
    (history[id] || []).forEach((p) => {
      if (!cutoff || p.timestamp >= cutoff) {
        allTimestamps.add(p.timestamp)
      }
    })
  })
  const sorted = [...allTimestamps].sort()
  if (sorted.length === 0) return []

  return sorted.map((ts) => {
    const row = { timestamp: toUTC8(ts) }
    probeIds.forEach((pid) => {
      const points = (history[pid] || []).filter((p) => p.timestamp === ts)
      if (points.length > 0) {
        row[`${pid}_${metricKey}`] = points[0][metricKey]
      }
    })
    return row
  })
}

function computeStats(data, probeIds, metricKey) {
  const stats = {}
  probeIds.forEach((pid) => {
    const vals = data.map((d) => d[`${pid}_${metricKey}`]).filter((v) => v != null)
    if (vals.length === 0) {
      stats[pid] = null
      return
    }
    const sum = vals.reduce((a, b) => a + b, 0)
    stats[pid] = {
      avg: sum / vals.length,
      min: Math.min(...vals),
      max: Math.max(...vals),
    }
  })
  return stats
}

function ChartTooltip({ active, payload, label, unit }) {
  if (!active || !payload || payload.length === 0) return null

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '8px 12px',
        fontSize: 12,
        minWidth: 140,
      }}
    >
      <div style={{ color: 'var(--gray)', fontSize: 10, marginBottom: 6 }}>{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
          <span style={{ color: entry.color }}>{entry.name}</span>
          <span style={{ color: 'var(--text-h)', fontWeight: 500 }}>
            {entry.value != null ? `${entry.value.toFixed(1)}${unit}` : '—'}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function ProbeTelemetry() {
  const [activeMetric, setActiveMetric] = useState('latency_ms')
  const visibleEndpoints = useMetricsStore((s) => s.visibleEndpoints)
  const endpointHistory = useMetricsStore((s) => s.endpointHistory || EMPTY_ARR)
  const timeWindow = useMetricsStore((s) => s.timeWindow)
  const setTimeWindow = useMetricsStore((s) => s.setTimeWindow)
  const toggleEndpointVisibility = useMetricsStore((s) => s.toggleEndpointVisibility)

  const allEndpointIds = Object.keys(visibleEndpoints).sort()
  const activeEndpoints = allEndpointIds.filter((id) => visibleEndpoints[id] !== false)

  const metric = METRICS.find((m) => m.key === activeMetric) || METRICS[0]
  const data = mergeSeries(activeEndpoints, timeWindow, endpointHistory, metric.key)
  const stats = computeStats(data, activeEndpoints, metric.key)

  return (
    <div
      className="rounded-lg p-3 flex flex-col gap-2"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center justify-between">
        <h2 style={{ margin: 0 }}>Link Telemetry</h2>
        {/* probe toggles */}
        <div className="flex items-center gap-1 text-xs">
          {allEndpointIds.map((pid) => {
            const on = visibleEndpoints[pid] !== false
            return (
              <button
                key={pid}
                onClick={() => toggleEndpointVisibility(pid)}
                className="rounded px-1.5 py-0.5 border transition-colors"
                style={{
                  background: on ? 'var(--accent-bg)' : 'transparent',
                  borderColor: on ? 'var(--accent)' : 'var(--border)',
                  color: on ? 'var(--accent)' : 'var(--gray)',
                  cursor: 'pointer',
                  fontSize: 10,
                }}
              >
                {pid}
              </button>
            )
          })}
        </div>
      </div>

      {/* metric tabs */}
      <div className="flex items-center gap-1">
        {METRICS.map((m) => {
          const active = activeMetric === m.key
          return (
            <button
              key={m.key}
              onClick={() => setActiveMetric(m.key)}
              className="rounded px-2 py-0.5 text-xs font-semibold transition-colors border"
              style={{
                background: active ? 'var(--accent-bg)' : 'transparent',
                borderColor: active ? 'var(--accent)' : 'var(--border)',
                color: active ? 'var(--accent)' : 'var(--gray)',
                cursor: 'pointer',
                fontSize: 10,
              }}
            >
              {m.label} ({m.unit})
            </button>
          )
        })}
      </div>

      {data.length === 0 ? (
        <div className="flex items-center justify-center" style={{ height: 180, color: 'var(--gray)' }}>
          <p className="text-sm">Waiting for endpoint metrics...</p>
        </div>
      ) : (
        <>
          {/* time window selectors */}
          <div className="flex items-center gap-1">
            {TIME_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setTimeWindow(opt.value)}
                className="rounded px-1.5 py-0.5 text-xs transition-colors"
                style={{
                  background: timeWindow === opt.value ? 'var(--accent-bg)' : 'transparent',
                  border: `1px solid ${timeWindow === opt.value ? 'var(--accent)' : 'var(--border)'}`,
                  color: timeWindow === opt.value ? 'var(--accent)' : 'var(--gray)',
                  cursor: 'pointer',
                  fontSize: 10,
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* chart */}
          <div style={{ height: 180 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="timestamp" tick={{ fontSize: 10, fill: 'var(--gray)' }} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10, fill: 'var(--gray)' }} width={36} />
                <Tooltip content={<ChartTooltip unit={metric.unit} />} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {activeEndpoints.map((pid, idx) => (
                  <Line
                    key={`${pid}_${metric.key}`}
                    type="monotone"
                    dataKey={`${pid}_${metric.key}`}
                    stroke={ENDPOINT_COLORS[idx % ENDPOINT_COLORS.length]}
                    strokeWidth={1.5}
                    dot={false}
                    name={pid}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* summary stats */}
          <div
            className="flex flex-col gap-1 text-xs px-2 py-1.5 rounded"
            style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}
          >
            {activeEndpoints.map((pid) => {
              const s = stats[pid]
              if (!s) return null
              return (
                <div key={pid} className="flex items-center gap-x-3 flex-wrap" style={{ lineHeight: 1.4 }}>
                  <span className="font-semibold" style={{ color: 'var(--text-h)', minWidth: 52 }}>
                    {pid}
                  </span>
                  <span style={{ color: 'var(--gray)', fontSize: 10, whiteSpace: 'nowrap' }}>
                    avg{' '}
                    <span style={{ color: 'var(--text)' }}>{s.avg.toFixed(1)}{metric.unit}</span>
                    {' '}min{' '}
                    <span style={{ color: 'var(--text)' }}>{s.min.toFixed(1)}{metric.unit}</span>
                    {' '}max{' '}
                    <span style={{ color: 'var(--text)' }}>{s.max.toFixed(1)}{metric.unit}</span>
                  </span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
