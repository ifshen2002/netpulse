import useWebSocket from './hooks/useWebSocket'
import useMetricsStore from './store/metricsStore'

const STATUS_COLORS = { green: '#22c55e', yellow: '#eab308', red: '#ef4444', gray: '#6b7280' }

function MetricRow({ nodeId, data }) {
  if (!data) return null
  return (
    <tr>
      <td style={{ fontWeight: 600 }}>{nodeId}</td>
      <td style={{ color: STATUS_COLORS[data.status] || '#888' }}>{data.status}</td>
      <td>{data.cpu.toFixed(1)}%</td>
      <td>{data.memory.toFixed(1)}%</td>
      <td>{data.disk.toFixed(1)}%</td>
      <td>{data.latency_ms.toFixed(1)}ms</td>
      <td>{data.packet_loss_pct.toFixed(1)}%</td>
    </tr>
  )
}

export default function App() {
  useWebSocket()
  const metrics = useMetricsStore((s) => s.metrics)
  const connected = useMetricsStore((s) => s.connected)

  return (
    <main style={{ maxWidth: 800, margin: '2rem auto', fontFamily: 'monospace' }}>
      <h1>NetPulse — Live Metrics</h1>
      <p>
        WebSocket: <span style={{ color: connected ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
          {connected ? 'CONNECTED' : 'DISCONNECTED'}
        </span>
      </p>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '1rem' }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #333', textAlign: 'left' }}>
            <th>Node</th><th>Status</th><th>CPU</th><th>Memory</th><th>Disk</th><th>Latency</th><th>Packet Loss</th>
          </tr>
        </thead>
        <tbody>
          {['node-1', 'node-2', 'node-3'].map((id) => (
            <MetricRow key={id} nodeId={id} data={metrics[id]} />
          ))}
        </tbody>
      </table>
    </main>
  )
}
