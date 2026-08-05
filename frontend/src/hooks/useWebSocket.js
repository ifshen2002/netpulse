import { useEffect, useRef } from 'react'
import useMetricsStore from '../store/metricsStore'
import { getAccessToken, getProjectId } from '../lib/api'

const MAX_RETRIES = 10
const RETRY_BASE_MS = 800

export default function useWebSocket() {
  const store = useMetricsStore
  const retries = useRef(0)
  const wsRef = useRef(null)
  const timerRef = useRef(null)

  useEffect(() => {
    let stopped = false

    function connect() {
      if (stopped || retries.current >= MAX_RETRIES) return

      const projectId = getProjectId()
      // Wait until we have both a token AND a project_id.
      // On first login, fetchProjectRole saves the project_id to
      // localStorage AFTER the login API returns. If we connect
      // before that, the WS will have no project_id and won't
      // receive project-scoped broadcasts.
      if (!projectId) {
        timerRef.current = setTimeout(connect, 500)
        return
      }

      const token = getAccessToken()
      if (!token) {
        timerRef.current = setTimeout(connect, 500)
        return
      }

      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const url = new URL(`${proto}//${location.host}/ws`)
      url.searchParams.set('access_token', token)
      url.searchParams.set('project_id', projectId)

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        retries.current = 0
        store.getState().setConnected(true)
        store.getState().fetchEndpoints()
        store.getState().fetchInitialEndpoints()
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
            case 'endpoint_metric_update':
              s.updateEndpointMetric(event)
              break
            case 'packet_evidence':
              s.updatePacketEvidence(event)
              break
            case 'endpoint_status_changed':
              s.updateEndpointStatus(event)
              break
            case 'notification_created':
              s.addNotification(event)
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
        timerRef.current = setTimeout(connect, delay)
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
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
    }
  }, [store])
}
