import { useEffect, useRef } from 'react'
import useMetricsStore from '../store/metricsStore'

const MAX_RETRIES = 5
const RETRY_BASE_MS = 1000

export default function useWebSocket() {
  const updateMetric = useMetricsStore((s) => s.updateMetric)
  const setConnected = useMetricsStore((s) => s.setConnected)
  const retries = useRef(0)
  const wsRef = useRef(null)

  useEffect(() => {
    let stopped = false

    function connect() {
      if (stopped || retries.current >= MAX_RETRIES) return

      const ws = new WebSocket('ws://localhost:8000/ws')
      wsRef.current = ws

      ws.onopen = () => {
        retries.current = 0
        setConnected(true)
      }

      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data)
          if (event.type === 'metric_update') {
            updateMetric(event)
          }
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        setConnected(false)
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
  }, [updateMetric, setConnected])
}
