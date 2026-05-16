import { create } from 'zustand'

const MAX_ALERTS = 20
const MAX_INCIDENTS = 20
const MAX_HISTORY = 60

const useMetricsStore = create((set, get) => ({
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

  // ── chart ring buffers ───────────────────────────────────────
  history: {},

  // ── alerts (last 20, newest first) ───────────────────────────
  alerts: [],

  addAlert: (event) =>
    set((state) => {
      const next = [
        {
          alert_id: event.alert_id,
          node_id: event.node_id,
          alert_type: event.alert_type,
          message: event.message,
          timestamp: event.timestamp,
        },
        ...state.alerts,
      ]
      if (next.length > MAX_ALERTS) next.length = MAX_ALERTS
      return { alerts: next }
    }),

  // ── incidents (last 20, newest first) ────────────────────────
  incidents: [],

  addIncident: (event) =>
    set((state) => {
      const next = [
        {
          incident_id: event.incident_id,
          title: event.title,
          node_id: event.node_id,
          status: 'open',
          timestamp: event.timestamp,
          alertCount: 1,
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

  setChaosState: (active, burst) => set({ chaosActive: active, burstNodes: burst }),

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
