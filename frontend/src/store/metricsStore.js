import { create } from 'zustand'

const MAX_ALERTS = 20
const MAX_INCIDENTS = 20
const MAX_HISTORY = 1500

// Stable empty array — prevents infinite re-render loops in selectors
// that use || [].  A fresh [] on every call breaks useSyncExternalStore's
// Object.is comparison because [] !== [].
export const EMPTY_ARR = Object.freeze([])

const useMetricsStore = create((set) => ({
  // ── live metrics (existing) ──────────────────────────────────
  metrics: {},
  connected: false,

  updateMetric: (event) =>
    set((state) => {
      const point = {
        timestamp: event.timestamp,
        cpu: event.cpu,
        memory: event.memory,
        latency_ms: event.latency_ms,
      }
      const prev = state.history[event.node_id] || []
      const next = [...prev, point]
      if (next.length > MAX_HISTORY) next.splice(0, next.length - MAX_HISTORY)

      return {
        metrics: {
          ...state.metrics,
          [event.node_id]: {
            cpu: event.cpu,
            memory: event.memory,
            disk: event.disk,
            latency_ms: event.latency_ms,
            packet_loss_pct: event.packet_loss_pct,
            status: event.status,
            timestamp: event.timestamp,
          },
        },
        history: {
          ...state.history,
          [event.node_id]: next,
        },
      }
    }),

  setConnected: (value) => set({ connected: value }),

  setNodeStatus: (node_id, status) =>
    set((state) => {
      const existing = state.metrics[node_id]
      if (!existing) return {}
      return {
        metrics: { ...state.metrics, [node_id]: { ...existing, status } },
      }
    }),

  // ── chart ring buffers ───────────────────────────────────────
  history: {},

  // ── alerts (last 20, newest first) ───────────────────────────
  alerts: [],

  addAlert: (event) =>
    set((state) => {
      const next = [
        {
          alert_id: event.alert_id,
          incident_id: event.incident_id,
          node_id: event.node_id,
          alert_type: event.alert_type,
          message: event.message,
          timestamp: event.timestamp,
        },
        ...state.alerts,
      ]
      if (next.length > MAX_ALERTS) next.length = MAX_ALERTS
      // Also update the matching incident with latest alert details
      const updatedIncidents = state.incidents.map((inc) => {
        if (inc.incident_id === event.incident_id) {
          return {
            ...inc,
            alertCount: inc.alertCount + 1,
            latestMessage: event.message,
            latestAlertAt: event.timestamp,
          }
        }
        return inc
      })
      return { alerts: next, incidents: updatedIncidents }
    }),

  // ── incidents (last 20, newest first) ────────────────────────
  incidents: [],

  addIncident: (event) =>
    set((state) => {
      const existing = state.incidents.find((i) => i.incident_id === event.incident_id)
      if (existing) return {}
      const next = [
        {
          incident_id: event.incident_id,
          title: event.title,
          node_id: event.node_id,
          status: 'open',
          timestamp: event.timestamp,
          alertCount: 0,  // will be bumped by addAlert
          latestMessage: null,
          latestAlertAt: null,
        },
        ...state.incidents,
      ]
      if (next.length > MAX_INCIDENTS) next.length = MAX_INCIDENTS
      return { incidents: next }
    }),

  bumpIncidentAlertCount: (incident_id) =>
    set((state) => ({
      incidents: state.incidents.map((inc) =>
        inc.incident_id === incident_id
          ? { ...inc, alertCount: inc.alertCount + 1 }
          : inc
      ),
    })),

  closeIncident: (event) =>
    set((state) => ({
      incidents: state.incidents.map((inc) =>
        inc.incident_id === event.incident_id
          ? { ...inc, status: 'closed', closedAt: event.timestamp }
          : inc
      ),
    })),

  // ── chaos state ──────────────────────────────────────────────
  chaosActive: {},
  burstNodes: {},

  chaosCount: 0,

  incrementChaosCount: () => set((state) => ({ chaosCount: state.chaosCount + 1 })),

  setChaosState: (active, burst) => set({ chaosActive: active, burstNodes: burst }),

  // ── node visibility ──────────────────────────────────────────
  visibleNodes: { 'node-1': true, 'node-2': true, 'node-3': true },

  toggleNodeVisibility: (nodeId) =>
    set((state) => ({
      visibleNodes: {
        ...state.visibleNodes,
        [nodeId]: !state.visibleNodes[nodeId],
      },
    })),

  // ── time window ─────────────────────────────────────────────
  timeWindow: 0, // 0 = all available, else minutes

  setTimeWindow: (minutes) => set({ timeWindow: minutes }),

  // ── initial data fetch ───────────────────────────────────────
  fetchChaosStatus: async () => {
    try {
      const resp = await fetch('/api/chaos/status')
      const json = await resp.json()
      if (json.success) {
        set({
          chaosActive: json.data.active || {},
          burstNodes: json.data.burst || {},
        })
      }
    } catch {
      // backend may not be ready on first load
    }
  },
}))

export default useMetricsStore
