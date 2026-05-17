import { useEffect, useRef } from 'react'
import useMetricsStore from '../store/metricsStore'

const MAX_RETRIES = 5
const RETRY_BASE_MS = 1000

export default function useWebSocket() {
  const store = useMetricsStore
  const retries = useRef(0)
  const wsRef = useRef(null)

  useEffect(() => {
    let stopped = false

    function connect() {
      if (stopped || retries.current >= MAX_RETRIES) return

      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${proto}//${location.host}/ws`)
      wsRef.current = ws

      ws.onopen = () => {
        retries.current = 0
        store.getState().setConnected(true)
        store.getState().fetchChaosStatus()
        store.getState().fetchInitialMetrics()
      }

      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data)
          const s = store.getState()
          switch (event.type) {
            case 'metric_update':
              s.updateMetric(event)
              break
            case 'alert_fired':
              s.addAlert(event)
              break
            case 'incident_opened':
              s.addIncident(event)
              break
            case 'incident_closed':
              s.closeIncident(event)
              break
            case 'node_status_changed':
              s.setNodeStatus(event.node_id, event.status)
              break
          }
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        store.getState().setConnected(false)
        wsRef.current = null
        if (stopped) return
        const delay = Math.min(RETRY_BASE_MS * 2 ** retries.current, 30000)
        retries.current += 1
        setTimeout(connect, delay)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      stopped = true
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [store])
}
