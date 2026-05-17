import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import useMetricsStore from '../store/metricsStore'
import { toUTC8 } from '../lib/time'

const METRIC_COLORS = {
  cpu: 'var(--green)',
  memory: 'var(--yellow)',
  latency_ms: 'var(--accent)',
  packet_loss_pct: 'var(--red)',
}

const NODE_DASHES = ['', '6 3', '2 2']

const KEYS = ['cpu', 'memory', 'latency_ms', 'packet_loss_pct']
const LABELS = { cpu: 'CPU %', memory: 'MEM %', latency_ms: 'Lat ms', packet_loss_pct: 'Loss %' }
const UNITS = { cpu: '%', memory: '%', latency_ms: 'ms', packet_loss_pct: '%' }
const ALL_NODES = ['node-1', 'node-2', 'node-3']
const NODE_LABELS = { 'node-1': 'Host', 'node-2': 'Svc-A', 'node-3': 'Svc-B' }

function mergeSeries(nodeIds, windowMinutes) {
  const { history } = useMetricsStore.getState()
  const cutoff = windowMinutes > 0
    ? new Date(Date.now() - windowMinutes * 60 * 1000).toISOString()
    : null

  const allTimestamps = new Set()
  nodeIds.forEach((id) => {
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
    nodeIds.forEach((nid) => {
      const points = (history[nid] || []).filter((p) => p.timestamp === ts)
      if (points.length > 0) {
        KEYS.forEach((k) => {
          row[`${nid}_${k}`] = points[0][k]
        })
      }
    })
    return row
  })
}

function computeStats(data, nodeIds) {
  const stats = {}
  nodeIds.forEach((nid) => {
    stats[nid] = {}
    KEYS.forEach((k) => {
      const vals = data.map((d) => d[`${nid}_${k}`]).filter((v) => v != null)
      if (vals.length === 0) {
        stats[nid][k] = null
        return
      }
      const sum = vals.reduce((a, b) => a + b, 0)
      stats[nid][k] = {
        avg: sum / vals.length,
        min: Math.min(...vals),
        max: Math.max(...vals),
      }
    })
  })
  return stats
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || payload.length === 0) return null

  const grouped = {}
  payload.forEach((entry) => {
    const parts = entry.dataKey.split('_')
    const node = parts.slice(0, -1).join('_')
    const key = parts[parts.length - 1]
    if (!grouped[node]) grouped[node] = []
    grouped[node].push({ key, value: entry.value, label: LABELS[key] || key, unit: UNITS[key] || '' })
  })

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '8px 12px',
        fontSize: 12,
        minWidth: 160,
      }}
    >
      <div style={{ color: 'var(--gray)', fontSize: 10, marginBottom: 6 }}>{label}</div>
      {Object.entries(grouped).map(([node, entries]) => (
        <div key={node} style={{ marginBottom: 4 }}>
          <div style={{ color: 'var(--text-h)', fontWeight: 600, fontSize: 11, marginBottom: 2 }}>
            {NODE_LABELS[node] || node}
          </div>
          {entries.map((e) => (
            <div key={e.key} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, paddingLeft: 8 }}>
              <span style={{ color: METRIC_COLORS[e.key] || 'var(--text)' }}>{e.label}</span>
              <span style={{ color: 'var(--text-h)', fontWeight: 500 }}>
                {e.value != null ? e.value.toFixed(1) : '—'}{e.unit}
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

const TIME_OPTIONS = [
  { label: 'ALL', value: 0 },
  { label: '1m', value: 1 },
  { label: '5m', value: 5 },
  { label: '15m', value: 15 },
  { label: '1h', value: 60 },
]

export default function MetricsChart() {
  const visibleNodes = useMetricsStore((s) => s.visibleNodes)
  const timeWindow = useMetricsStore((s) => s.timeWindow)
  const setTimeWindow = useMetricsStore((s) => s.setTimeWindow)
  const activeNodes = ALL_NODES.filter((id) => visibleNodes[id] !== false)
  const data = mergeSeries(activeNodes, timeWindow)
  const stats = computeStats(data, activeNodes)

  if (data.length === 0) {
    return (
      <div className="h-full flex items-center justify-center" style={{ color: 'var(--gray)' }}>
        <p className="text-sm">Waiting for metrics...</p>
      </div>
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 4 }}>
      {/* time window selectors */}
      <div className="flex items-center gap-1" style={{ paddingLeft: 4 }}>
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
      <div style={{ flex: 1 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" tick={{ fontSize: 10, fill: 'var(--gray)' }} interval="preserveStartEnd" />
            <YAxis yAxisId="pct" tick={{ fontSize: 10, fill: 'var(--gray)' }} width={32} domain={[0, 100]} />
            <YAxis yAxisId="ms" orientation="right" tick={{ fontSize: 10, fill: 'var(--gray)' }} width={32} />
            <Tooltip content={<ChartTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {activeNodes.map((nid, ni) =>
              KEYS.map((key) => (
                <Line
                  key={`${nid}_${key}`}
                  type="monotone"
                  dataKey={`${nid}_${key}`}
                  yAxisId={key === 'latency_ms' ? 'ms' : 'pct'}
                  stroke={METRIC_COLORS[key]}
                  strokeWidth={key === 'packet_loss_pct' ? 1 : 1.5}
                  strokeDasharray={NODE_DASHES[ni]}
                  dot={false}
                  name={`${NODE_LABELS[nid]} ${LABELS[key]}`}
                  connectNulls
                />
              ))
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* summary — stacked per-node rows, metrics wrap naturally */}
      <div
        className="flex flex-col gap-1 text-xs px-2 py-1.5 rounded"
        style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}
      >
        {activeNodes.map((nid) => (
          <div key={nid} className="flex items-center gap-x-3 gap-y-0.5 flex-wrap" style={{ lineHeight: 1.4 }}>
            <span className="font-semibold" style={{ color: 'var(--text-h)', minWidth: 36 }}>
              {NODE_LABELS[nid]}
            </span>
            {KEYS.map((k) => {
              const s = stats[nid]?.[k]
              if (!s) return null
              const unit = UNITS[k]
              return (
                <span key={k} style={{ color: 'var(--gray)', fontSize: 10, whiteSpace: 'nowrap' }}>
                  <span style={{ color: METRIC_COLORS[k] }}>{LABELS[k]}</span>
                  <span style={{ color: 'var(--text)' }}>
                    {' '}{s.avg.toFixed(1)}{unit}
                  </span>
                  <span style={{ color: 'var(--gray)', opacity: 0.6 }}>
                    {' '}{s.min.toFixed(0)}{unit}–{s.max.toFixed(0)}{unit}
                  </span>
                </span>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
