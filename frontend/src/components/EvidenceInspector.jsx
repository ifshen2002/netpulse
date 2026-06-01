import useMetricsStore from '../store/metricsStore'
import { toUTC8 } from '../lib/time'

function EvidenceTimeline({ records, chaosStartedAt }) {
  if (!records || records.length === 0) {
    return (
      <p className="text-xs" style={{ color: 'var(--gray)', padding: '4px 0' }}>
        No evidence history yet.
      </p>
    )
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 10,
          fontFamily: 'var(--mono)',
        }}
      >
        <thead>
          <tr>
            {['Evidence ID', 'Time', 'RTT', 'TTL', 'Seq', 'Size'].map((h) => (
              <th
                key={h}
                className="text-left px-1 py-0.5"
                style={{ color: 'var(--gray)', fontWeight: 500, fontSize: 9, borderBottom: '1px solid var(--border)' }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {records.map((e, i) => {
            const isChaos = chaosStartedAt && e.timestamp >= chaosStartedAt
            return (
              <tr
                key={i}
                style={{
                  borderBottom: '1px solid var(--border)',
                  background: isChaos ? 'rgba(239,68,68,0.06)' : 'transparent',
                }}
              >
                <td className="px-1 py-0.5" style={{ color: 'var(--gray)', fontSize: 9 }}>
                  {e.evidence_id ? e.evidence_id.slice(0, 12) : '—'}
                </td>
                <td className="px-1 py-0.5" style={{ color: 'var(--gray)', fontSize: 9 }}>
                  {toUTC8(e.timestamp)}
                </td>
                <td className="px-1 py-0.5" style={{ color: isChaos ? 'var(--red)' : 'var(--text-h)', fontWeight: isChaos ? 700 : 500 }}>
                  {e.rtt_ms != null ? `${e.rtt_ms.toFixed(1)}ms` : '—'}
                </td>
                <td className="px-1 py-0.5" style={{ color: 'var(--text)' }}>{e.ttl ?? '—'}</td>
                <td className="px-1 py-0.5" style={{ color: 'var(--text)' }}>{e.icmp_seq ?? '—'}</td>
                <td className="px-1 py-0.5" style={{ color: 'var(--text)' }}>{e.packet_size_bytes != null ? `${e.packet_size_bytes}B` : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function EvidenceInspector({ probeId }) {
  const packetEvidence = useMetricsStore((s) => s.packetEvidence)
  const packetEvidenceTimeline = useMetricsStore((s) => s.packetEvidenceTimeline)
  const probeMetrics = useMetricsStore((s) => s.probeMetrics)
  const alerts = useMetricsStore((s) => s.alerts)
  const incidents = useMetricsStore((s) => s.incidents)

  const evidence = packetEvidence[probeId]
  const metrics = probeMetrics[probeId]
  const timeline = [...(packetEvidenceTimeline[probeId] || [])].reverse()

  if (!evidence) {
    return (
      <div className="rounded p-3" style={{ background: 'var(--bg)', border: '1px solid var(--border)' }}>
        <p className="text-xs" style={{ color: 'var(--gray)' }}>No evidence available for {probeId}.</p>
      </div>
    )
  }

  // Find related alerts for this probe
  const relatedAlerts = alerts.filter((a) => a.probe_id === probeId)

  // Find related incidents
  const relatedIncidents = incidents.filter((i) => i.probe_id === probeId)

  // Derive alert evaluation info
  const latencyThreshold = 300
  const lossThreshold = 5
  const availThreshold = 95

  let latencyResult = 'OK'
  let lossResult = 'OK'
  let availResult = 'OK'

  if (metrics) {
    if (metrics.latency_ms > latencyThreshold) latencyResult = 'ALERT'
    if (metrics.packet_loss_pct >= lossThreshold) lossResult = 'ALERT'
    if (metrics.availability_pct <= availThreshold) availResult = 'ALERT'
  }

  return (
    <div className="rounded p-3 flex flex-col gap-3" style={{ background: 'var(--bg)', borderLeft: '3px solid var(--accent)' }}>
      {/* Header */}
      <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--gray)' }}>
        <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{probeId}</span>
        <span>&rarr;</span>
        <span>Packet Evidence</span>
        <span className="rounded px-1 text-xs" style={{ background: 'var(--accent-bg)', color: 'var(--accent)', fontFamily: 'var(--mono)', fontSize: 9 }}>
          {evidence.evidence_id?.slice(0, 12) || '—'}
        </span>
        <span>&rarr;</span>
        <span>Metric</span>
        <span>&rarr;</span>
        <span>Alert</span>
        <span>&rarr;</span>
        <span>Incident</span>
      </div>

      {/* Section 1: Raw Probe Result */}
      <div>
        <h4 className="text-xs font-semibold mb-1" style={{ color: 'var(--text-h)' }}>1. Raw Probe Result</h4>
        <pre
          className="rounded px-2 py-1.5 text-xs"
          style={{
            background: '#0d1117',
            color: '#c9d1d9',
            fontFamily: 'var(--mono)',
            fontSize: 10,
            lineHeight: 1.5,
            overflowX: 'auto',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            margin: 0,
          }}
        >
          {evidence.raw_output || '(no raw output captured)'}
        </pre>
      </div>

      {/* Section 2: Parsed Evidence */}
      <div>
        <h4 className="text-xs font-semibold mb-1" style={{ color: 'var(--text-h)' }}>2. Parsed Evidence</h4>
        <div
          className="rounded px-2 py-1.5 grid grid-cols-4 gap-x-4 gap-y-1 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        >
          {[
            ['RTT', `${evidence.rtt_ms?.toFixed(1)} ms`],
            ['TTL', evidence.ttl],
            ['Sequence', evidence.icmp_seq],
            ['Packet Size', `${evidence.packet_size_bytes} B`],
            ['Source IP', evidence.src_ip],
            ['Destination IP', evidence.dst_ip || evidence.endpoint],
            ['Protocol', (evidence.protocol || 'icmp').toUpperCase()],
            ['Timestamp', evidence.timestamp ? toUTC8(evidence.timestamp) : '—'],
          ].map(([label, value]) => (
            <div key={label} className="flex gap-1">
              <span style={{ color: 'var(--gray)' }}>{label}:</span>
              <span style={{ color: 'var(--text-h)', fontWeight: 500, fontFamily: 'var(--mono)', fontSize: 10 }}>{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Section 3: Metric Derivation */}
      <div>
        <h4 className="text-xs font-semibold mb-1" style={{ color: 'var(--text-h)' }}>3. Metric Derivation</h4>
        <div
          className="rounded px-2 py-1.5 text-xs flex flex-col gap-0.5"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        >
          {metrics ? (
            <>
              <div className="flex gap-2">
                <span style={{ color: 'var(--gray)', minWidth: '14ch' }}>Latency:</span>
                <span style={{ color: 'var(--accent)', fontWeight: 500 }}>RTT = {metrics.latency_ms.toFixed(1)} ms</span>
              </div>
              <div className="flex gap-2">
                <span style={{ color: 'var(--gray)', minWidth: '14ch' }}>Packet Loss:</span>
                <span style={{ color: metrics.packet_loss_pct > 0 ? 'var(--yellow)' : 'var(--green)', fontWeight: 500 }}>
                  {metrics.packet_loss_pct.toFixed(1)}%
                </span>
                <span className="text-xs" style={{ color: 'var(--gray)' }}>
                  (unanswered / total probes in window)
                </span>
              </div>
              <div className="flex gap-2">
                <span style={{ color: 'var(--gray)', minWidth: '14ch' }}>Availability:</span>
                <span style={{ color: metrics.availability_pct >= 95 ? 'var(--green)' : 'var(--yellow)', fontWeight: 500 }}>
                  {metrics.availability_pct.toFixed(1)}%
                </span>
                <span className="text-xs" style={{ color: 'var(--gray)' }}>
                  (successful / total probes in window)
                </span>
              </div>
              <div className="flex gap-2">
                <span style={{ color: 'var(--gray)', minWidth: '14ch' }}>Status:</span>
                <span style={{ color: 'var(--text-h)', fontWeight: 600 }}>{metrics.status?.toUpperCase()}</span>
              </div>
            </>
          ) : (
            <span style={{ color: 'var(--gray)' }}>No derived metrics yet.</span>
          )}
        </div>
      </div>

      {/* Section 4: Alert Evaluation */}
      <div>
        <h4 className="text-xs font-semibold mb-1" style={{ color: 'var(--text-h)' }}>4. Alert Evaluation</h4>
        <div
          className="rounded px-2 py-1.5 text-xs flex flex-col gap-1"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        >
          {metrics ? (
            <>
              <div className="flex items-center gap-2">
                <span style={{ color: 'var(--gray)', minWidth: '16ch' }}>Latency Critical:</span>
                <span style={{ color: 'var(--text-h)' }}>threshold {latencyThreshold}ms</span>
                <span style={{ color: 'var(--gray)' }}>&rarr;</span>
                <span style={{ color: 'var(--text-h)', fontFamily: 'var(--mono)' }}>
                  observed {metrics.latency_ms.toFixed(1)}ms
                </span>
                <span>&rarr;</span>
                <span
                  className="rounded px-1 py-0.5 text-xs font-semibold"
                  style={{
                    background: latencyResult === 'ALERT' ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.12)',
                    color: latencyResult === 'ALERT' ? 'var(--red)' : 'var(--green)',
                    border: `1px solid ${latencyResult === 'ALERT' ? 'var(--red)' : 'var(--green)'}`,
                    fontSize: 9,
                  }}
                >
                  {latencyResult}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span style={{ color: 'var(--gray)', minWidth: '16ch' }}>Packet Loss Critical:</span>
                <span style={{ color: 'var(--text-h)' }}>threshold {lossThreshold}%</span>
                <span style={{ color: 'var(--gray)' }}>&rarr;</span>
                <span style={{ color: 'var(--text-h)', fontFamily: 'var(--mono)' }}>
                  observed {metrics.packet_loss_pct.toFixed(1)}%
                </span>
                <span>&rarr;</span>
                <span
                  className="rounded px-1 py-0.5 text-xs font-semibold"
                  style={{
                    background: lossResult === 'ALERT' ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.12)',
                    color: lossResult === 'ALERT' ? 'var(--red)' : 'var(--green)',
                    border: `1px solid ${lossResult === 'ALERT' ? 'var(--red)' : 'var(--green)'}`,
                    fontSize: 9,
                  }}
                >
                  {lossResult}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span style={{ color: 'var(--gray)', minWidth: '16ch' }}>Availability Low:</span>
                <span style={{ color: 'var(--text-h)' }}>threshold {availThreshold}%</span>
                <span style={{ color: 'var(--gray)' }}>&rarr;</span>
                <span style={{ color: 'var(--text-h)', fontFamily: 'var(--mono)' }}>
                  observed {metrics.availability_pct.toFixed(1)}%
                </span>
                <span>&rarr;</span>
                <span
                  className="rounded px-1 py-0.5 text-xs font-semibold"
                  style={{
                    background: availResult === 'ALERT' ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.12)',
                    color: availResult === 'ALERT' ? 'var(--red)' : 'var(--green)',
                    border: `1px solid ${availResult === 'ALERT' ? 'var(--red)' : 'var(--green)'}`,
                    fontSize: 9,
                  }}
                >
                  {availResult}
                </span>
              </div>
            </>
          ) : (
            <span style={{ color: 'var(--gray)' }}>No metrics to evaluate.</span>
          )}
        </div>
      </div>

      {/* Section 5: Incident Correlation */}
      <div>
        <h4 className="text-xs font-semibold mb-1" style={{ color: 'var(--text-h)' }}>5. Incident Correlation</h4>
        <div
          className="rounded px-2 py-1.5 text-xs"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
        >
          {relatedAlerts.length === 0 && relatedIncidents.length === 0 ? (
            <span style={{ color: 'var(--gray)' }}>No alerts or incidents for this probe.</span>
          ) : (
            <div className="flex flex-col gap-1">
              {relatedAlerts.length > 0 && (
                <div className="flex flex-col gap-0.5">
                  <span style={{ color: 'var(--gray)', fontWeight: 500 }}>Related Alerts ({relatedAlerts.length}):</span>
                  {relatedAlerts.slice(0, 5).map((a) => (
                    <div key={a.alert_id} className="flex gap-2 text-xs" style={{ fontFamily: 'var(--mono)', fontSize: 9 }}>
                      <span style={{ color: 'var(--accent)' }}>{a.alert_id?.slice(0, 12)}</span>
                      <span style={{ color: 'var(--text-h)' }}>{a.alert_type}</span>
                      <span style={{ color: 'var(--gray)' }}>{a.message}</span>
                    </div>
                  ))}
                </div>
              )}
              {relatedIncidents.length > 0 && (
                <div className="flex flex-col gap-0.5 mt-1">
                  <span style={{ color: 'var(--gray)', fontWeight: 500 }}>Related Incidents ({relatedIncidents.length}):</span>
                  {relatedIncidents.map((inc) => (
                    <div key={inc.incident_id} className="flex gap-2 text-xs" style={{ fontFamily: 'var(--mono)', fontSize: 9 }}>
                      <span style={{ color: 'var(--accent)' }}>{inc.incident_id?.slice(0, 12)}</span>
                      <span style={{ color: 'var(--text-h)' }}>{inc.title}</span>
                      <span
                        className="rounded px-1 text-xs font-semibold"
                        style={{
                          background: inc.status === 'open' ? 'rgba(239,68,68,0.12)' : 'rgba(34,197,94,0.08)',
                          color: inc.status === 'open' ? 'var(--red)' : 'var(--green)',
                          fontSize: 8,
                        }}
                      >
                        {inc.status?.toUpperCase()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Evidence Timeline */}
      <div>
        <h4 className="text-xs font-semibold mb-1" style={{ color: 'var(--text-h)' }}>
          Evidence History ({timeline.length} records)
        </h4>
        <EvidenceTimeline records={timeline} />
      </div>
    </div>
  )
}
