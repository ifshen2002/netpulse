import { useState, useEffect, useRef } from 'react'
import useMetricsStore from '../store/metricsStore'
import { toUTC8 } from '../lib/time'
import EvidenceInspector from './EvidenceInspector'

const COLS = [
  { key: 'endpoint', label: 'Endpoint', width: '14ch' },
  { key: 'protocol', label: 'Proto', width: '6ch' },
  { key: 'src_ip', label: 'Src IP', width: '14ch' },
  { key: 'dst_ip', label: 'Dst IP', width: '14ch' },
  { key: 'rtt_ms', label: 'RTT', width: '8ch' },
  { key: 'packet_size_bytes', label: 'Size', width: '6ch' },
  { key: 'ttl', label: 'TTL', width: '5ch' },
  { key: 'icmp_seq', label: 'Seq', width: '5ch' },
  { key: 'timestamp', label: 'Time', width: '9ch' },
]

export default function PacketEvidencePanel() {
  const packetEvidence = useMetricsStore((s) => s.packetEvidence)
  const fetchEvidenceTimeline = useMetricsStore((s) => s.fetchEvidenceTimeline)
  const endpointIds = Object.keys(packetEvidence).sort()
  const [expanded, setExpanded] = useState(null)
  const fetchedRef = useRef({})

  useEffect(() => {
    for (const eid of endpointIds) {
      if (!fetchedRef.current[eid]) {
        fetchedRef.current[eid] = true
        fetchEvidenceTimeline(eid, 20)
      }
    }
  }, [endpointIds, fetchEvidenceTimeline])

  return (
    <div
      className="rounded-lg p-3"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border)' }}
    >
      <h2>Packet Evidence</h2>

      {endpointIds.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--gray)' }}>
          Waiting for probe data...
        </p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: 11,
              fontFamily: 'var(--mono)',
            }}
          >
            <thead>
              <tr>
                <th style={{ width: '3ch', borderBottom: '1px solid var(--border)' }} />
                {COLS.map((c) => (
                  <th
                    key={c.key}
                    className="text-left px-1.5 py-1"
                    style={{
                      color: 'var(--gray)',
                      fontWeight: 500,
                      fontSize: 10,
                      borderBottom: '1px solid var(--border)',
                      width: c.width,
                    }}
                  >
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {endpointIds.map((eid) => {
                const e = packetEvidence[eid]
                const isExpanded = expanded === eid

                return (
                  <tr key={eid} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-1 py-1">
                      <button
                        onClick={() => setExpanded(isExpanded ? null : eid)}
                        className="rounded text-xs font-bold"
                        style={{
                          background: isExpanded ? 'var(--accent-bg)' : 'transparent',
                          border: `1px solid ${isExpanded ? 'var(--accent)' : 'var(--border)'}`,
                          color: isExpanded ? 'var(--accent)' : 'var(--gray)',
                          cursor: 'pointer',
                          width: 18,
                          height: 18,
                          lineHeight: '16px',
                          padding: 0,
                          textAlign: 'center',
                        }}
                      >
                        {isExpanded ? '−' : '+'}
                      </button>
                    </td>
                    <td className="px-1.5 py-1" style={{ color: 'var(--text-h)', fontWeight: 500 }}>
                      {eid}
                    </td>
                    <td className="px-1.5 py-1" style={{ color: 'var(--accent)' }}>
                      {e.protocol?.toUpperCase()}
                    </td>
                    <td className="px-1.5 py-1" style={{ color: 'var(--text)' }}>
                      {e.src_ip}
                    </td>
                    <td className="px-1.5 py-1" style={{ color: 'var(--text)' }}>
                      {e.dst_ip || e.endpoint}
                    </td>
                    <td className="px-1.5 py-1" style={{ color: 'var(--text-h)' }}>
                      {e.rtt_ms != null ? `${e.rtt_ms.toFixed(1)}ms` : '—'}
                    </td>
                    <td className="px-1.5 py-1" style={{ color: 'var(--text)' }}>
                      {e.packet_size_bytes != null ? `${e.packet_size_bytes}B` : '—'}
                    </td>
                    <td className="px-1.5 py-1" style={{ color: 'var(--text)' }}>
                      {e.ttl ?? '—'}
                    </td>
                    <td className="px-1.5 py-1" style={{ color: 'var(--text)' }}>
                      {e.icmp_seq ?? '—'}
                    </td>
                    <td className="px-1.5 py-1" style={{ color: 'var(--gray)', fontSize: 10 }}>
                      {e.timestamp ? toUTC8(e.timestamp) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {/* Expanded Evidence Inspector for selected probe */}
          {expanded != null && (
            <div style={{ marginTop: 0 }}>
              <EvidenceInspector endpointId={expanded} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
