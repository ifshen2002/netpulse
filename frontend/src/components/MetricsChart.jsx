import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import useMetricsStore from '../store/metricsStore'

const COLORS = ['var(--green)', 'var(--yellow)', 'var(--accent)']
const KEYS = ['cpu', 'memory', 'latency_ms']
const LABELS = { cpu: 'CPU %', memory: 'MEM %', latency_ms: 'Lat ms' }
const NODE_IDS = ['node-1', 'node-2', 'node-3']

function mergeSeries() {
  const { history } = useMetricsStore.getState()
  const allTimestamps = new Set()
  NODE_IDS.forEach((id) => {
    (history[id] || []).forEach((p) => allTimestamps.add(p.timestamp))
  })
  const sorted = [...allTimestamps].sort()
  if (sorted.length === 0) return []

  return sorted.map((ts) => {
    const row = { timestamp: ts.slice(11, 19) }
    NODE_IDS.forEach((nid) => {
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

export default function MetricsChart() {
  const history = useMetricsStore((s) => s.history)
  const data = mergeSeries()

  if (data.length === 0) {
    return (
      <div className="h-full flex items-center justify-center" style={{ color: 'var(--gray)' }}>
        <p className="text-sm">Waiting for metrics...</p>
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
        <XAxis dataKey="timestamp" tick={{ fontSize: 10, fill: 'var(--gray)' }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10, fill: 'var(--gray)' }} width={32} />
        <Tooltip
          contentStyle={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            fontSize: 12,
          }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {NODE_IDS.map((nid, i) =>
          KEYS.map((key) => (
            <Line
              key={`${nid}_${key}`}
              type="monotone"
              dataKey={`${nid}_${key}`}
              stroke={COLORS[i]}
              strokeWidth={1.5}
              dot={false}
              name={`${nid} ${LABELS[key]}`}
              connectNulls
            />
          ))
        )}
      </LineChart>
    </ResponsiveContainer>
  )
}
