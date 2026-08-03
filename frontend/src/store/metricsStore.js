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
          endpoint_id: event.endpoint_id,
          alert_type: event.alert_type,
          message: event.message,
          evidence_id: event.evidence_id,
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
          endpoint_id: event.endpoint_id,
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

  // ── stress test placeholder ────────────────────────────────────
  stressCount: 0,

  incrementStressCount: () => set((state) => ({ stressCount: state.stressCount + 1 })),

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

  // ── node targets (configurable sources for node-2/3) ─────────
  nodeTargets: {
    'node-2': { type: 'simulated' },
    'node-3': { type: 'simulated' },
  },

  setNodeTarget: (nodeId, target) =>
    set((state) => ({
      nodeTargets: { ...state.nodeTargets, [nodeId]: target },
    })),

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

  // ── V2 endpoint state ─────────────────────────────────────
  endpoints: [],

  setEndpoints: (list) => set({ endpoints: list }),

  fetchEndpoints: async () => {
    try {
      const resp = await fetch('/api/endpoints')
      const json = await resp.json()
      if (json.success) {
        set({ endpoints: json.data })
      }
    } catch {
      // backend may not be ready
    }
  },

  // ── V2 endpoint telemetry state ─────────────────────────────
  endpointMetrics: {},
  endpointHistory: {},
  packetEvidence: {},
  packetEvidenceTimeline: {},   // { [endpoint_id]: [...recent records] }
  endpointStatuses: {},
  activeView: 'link',
  visibleEndpoints: {},

  // ── V2 network chaos ──────────────────────────────────────
  networkChaos: null,
  lastChaosSession: null,

  setNetworkChaos: (data) =>
    set((state) => {
      const prev = state.networkChaos
      return {
        networkChaos: data,
        lastChaosSession: prev && !data ? prev : state.lastChaosSession,
      }
    }),

  fetchNetworkChaosStatus: async () => {
    try {
      const resp = await fetch('/api/chaos/network/status')
      const json = await resp.json()
      if (json.success) {
        set({ networkChaos: json.data })
      }
    } catch {
      // backend may not be ready
    }
  },

  updateEndpointMetric: (event) =>
    set((state) => {
      const point = {
        timestamp: event.timestamp,
        latency_ms: event.latency_ms,
        packet_loss_pct: event.packet_loss_pct,
        availability_pct: event.availability_pct,
      }
      const prev = state.endpointHistory[event.endpoint_id] || []
      const next = [...prev, point]
      if (next.length > MAX_HISTORY) next.splice(0, next.length - MAX_HISTORY)

      const nextVE = { ...state.visibleEndpoints }
      if (!(event.endpoint_id in nextVE)) nextVE[event.endpoint_id] = true

      return {
        endpointMetrics: {
          ...state.endpointMetrics,
          [event.endpoint_id]: {
            latency_ms: event.latency_ms,
            packet_loss_pct: event.packet_loss_pct,
            availability_pct: event.availability_pct,
            status: event.status,
            endpoint: event.endpoint,
            timestamp: event.timestamp,
          },
        },
        endpointHistory: {
          ...state.endpointHistory,
          [event.endpoint_id]: next,
        },
        visibleEndpoints: nextVE,
      }
    }),

  updatePacketEvidence: (event) =>
    set((state) => {
      const nextVE = { ...state.visibleEndpoints }
      if (!(event.endpoint_id in nextVE)) nextVE[event.endpoint_id] = true
      const record = {
        evidence_id: event.evidence_id,
        protocol: event.protocol,
        src_ip: event.src_ip,
        dst_ip: event.dst_ip,
        ttl: event.ttl,
        packet_size_bytes: event.packet_size_bytes,
        icmp_seq: event.icmp_seq,
        rtt_ms: event.rtt_ms,
        timestamp: event.timestamp,
        endpoint: event.endpoint,
        raw_output: event.raw_output || '',
      }
      const prevTimeline = state.packetEvidenceTimeline[event.endpoint_id] || []
      const nextTimeline = [...prevTimeline, record]
      if (nextTimeline.length > 30) nextTimeline.splice(0, nextTimeline.length - 30)

      return {
        packetEvidence: {
          ...state.packetEvidence,
          [event.endpoint_id]: record,
        },
        packetEvidenceTimeline: {
          ...state.packetEvidenceTimeline,
          [event.endpoint_id]: nextTimeline,
        },
        visibleEndpoints: nextVE,
      }
    }),

  updateEndpointStatus: (event) =>
    set((state) => {
      const eid = event.endpoint_id
      const existing = state.endpointMetrics[eid]
      const nextMetrics = existing
        ? { ...state.endpointMetrics, [eid]: { ...existing, status: event.status } }
        : state.endpointMetrics
      return {
        endpointStatuses: { ...state.endpointStatuses, [eid]: event.status },
        endpointMetrics: nextMetrics,
      }
    }),

  setActiveView: (view) => set({ activeView: view }),

  toggleEndpointVisibility: (endpointId) =>
    set((state) => ({
      visibleEndpoints: {
        ...state.visibleEndpoints,
        [endpointId]: !state.visibleEndpoints[endpointId],
      },
    })),

  fetchInitialEndpoints: async () => {
    try {
      const resp = await fetch('/api/endpoints')
      const json = await resp.json()
      if (!json.success) return
      const endpoints = json.data || []

      set((state) => {
        const next = { ...state.visibleEndpoints }
        for (const ep of endpoints) {
          if (!(ep.id in next)) next[ep.id] = true
        }
        return { visibleEndpoints: next }
      })

      // Fetch initial metrics for each endpoint
      for (const ep of endpoints) {
        try {
          const mResp = await fetch(`/api/endpoints/${ep.id}/metrics?seconds=120`)
          const mJson = await mResp.json()
          if (mJson.success && mJson.data.metrics.length > 0) {
            const points = mJson.data.metrics.reverse().map((d) => ({
              timestamp: d.timestamp,
              latency_ms: d.latency_ms,
              packet_loss_pct: d.packet_loss_pct,
              availability_pct: d.availability_pct,
            }))
            set((state) => ({
              endpointHistory: {
                ...state.endpointHistory,
                [ep.id]: points.slice(-MAX_HISTORY),
              },
            }))
          }
        } catch {
          // endpoint may not have metrics yet
        }
      }

      // Fetch latest packet evidence for each endpoint
      for (const ep of endpoints) {
        try {
          const eResp = await fetch(`/api/endpoints/${ep.id}/evidence?limit=1`)
          const eJson = await eResp.json()
          if (eJson.success && eJson.data.evidence.length > 0) {
            const e = eJson.data.evidence[0]
            set((state) => ({
              packetEvidence: {
                ...state.packetEvidence,
                [ep.id]: {
                  protocol: e.protocol,
                  src_ip: e.src_ip,
                  dst_ip: e.dst_ip,
                  ttl: e.ttl,
                  packet_size_bytes: e.packet_size_bytes,
                  icmp_seq: e.icmp_seq,
                  rtt_ms: e.rtt_ms,
                  timestamp: e.timestamp,
                  endpoint: ep.target_host,
                },
              },
            }))
          }
        } catch {
          // no evidence yet
        }
      }
    } catch {
      // backend may not be ready
    }
  },

  fetchInitialMetrics: async () => {
    const nodeIds = ['node-1', 'node-2', 'node-3']
    const results = await Promise.allSettled(
      nodeIds.map(async (nid) => {
        const resp = await fetch(`/api/metrics/${nid}?limit=60`)
        const json = await resp.json()
        return { nodeId: nid, data: json.data || [] }
      }),
    )
    set((state) => {
      const nextMetrics = { ...state.metrics }
      const nextHistory = { ...state.history }
      for (const r of results) {
        if (r.status !== 'fulfilled' || !r.value.data.length) continue
        const { nodeId, data } = r.value
        // data is newest-first from API; reverse to oldest-first for history
        const points = data.reverse().map((d) => ({
          timestamp: d.timestamp,
          cpu: d.cpu,
          memory: d.memory,
          latency_ms: d.latency_ms,
        }))
        // Only set if WebSocket hasn't already populated more data
        const existing = state.history[nodeId]
        if (!existing || existing.length < points.length) {
          nextHistory[nodeId] = points.slice(-MAX_HISTORY)
        }
        // Only set latest snapshot if WebSocket hasn't already set one
        if (!state.metrics[nodeId]) {
          const latest = data[data.length - 1]
          nextMetrics[nodeId] = {
            cpu: latest.cpu,
            memory: latest.memory,
            disk: latest.disk,
            latency_ms: latest.latency_ms,
            packet_loss_pct: latest.packet_loss_pct,
            status: latest.status,
            timestamp: latest.timestamp,
          }
        }
      }
      return { metrics: nextMetrics, history: nextHistory }
    })
  },

  // ── notifications ────────────────────────────────────────
  notifications: [],
  unreadCount: 0,

  addNotification: (event) =>
    set((state) => {
      // Only add if this notification is for the current user (filtered client-side
      // since broadcast goes to all connected clients)
      const session = JSON.parse(localStorage.getItem('netpulse.session') || 'null')
      if (!session || session.user?.id !== event.user_id) return state
      const exists = state.notifications.some((n) => n.id === event.notification_id)
      if (exists) return state
      const entry = {
        id: event.notification_id,
        alert_id: event.alert_id,
        incident_id: event.incident_id,
        project_id: event.project_id,
        title: event.title,
        body: event.body,
        severity: event.severity,
        status: 'unread',
        created_at: new Date().toISOString(),
      }
      return {
        notifications: [entry, ...state.notifications].slice(0, 50),
        unreadCount: state.unreadCount + 1,
      }
    }),

  fetchNotifications: async () => {
    try {
      const resp = await fetch('/api/notifications?limit=50')
      const json = await resp.json()
      if (json.success) {
        const unread = json.data.filter((n) => n.status === 'unread').length
        set({ notifications: json.data, unreadCount: unread })
      }
    } catch {
      // backend may not be ready
    }
  },

  markNotificationRead: async (notificationId) => {
    try {
      const resp = await fetch(`/api/notifications/${notificationId}/read`, { method: 'PATCH' })
      const json = await resp.json()
      if (json.success) {
        set((state) => ({
          notifications: state.notifications.map((n) =>
            n.id === notificationId ? { ...n, status: 'read' } : n
          ),
          unreadCount: Math.max(0, state.unreadCount - 1),
        }))
      }
    } catch {
      // network error
    }
  },

  acknowledgeNotification: async (notificationId) => {
    try {
      const resp = await fetch(`/api/notifications/${notificationId}/acknowledge`, { method: 'PATCH' })
      const json = await resp.json()
      if (json.success) {
        set((state) => ({
          notifications: state.notifications.map((n) =>
            n.id === notificationId ? { ...n, status: 'acknowledged' } : n
          ),
        }))
      }
    } catch {
      // network error
    }
  },

  fetchEvidenceTimeline: async (endpointId, limit = 20) => {
    try {
      const resp = await fetch(`/api/endpoints/${endpointId}/evidence?limit=${limit}`)
      const json = await resp.json()
      if (!json.success || !json.data.evidence.length) return
      const records = json.data.evidence.reverse().map((e) => ({
        evidence_id: e.id,
        protocol: e.protocol,
        src_ip: e.src_ip,
        dst_ip: e.dst_ip,
        ttl: e.ttl,
        packet_size_bytes: e.packet_size_bytes,
        icmp_seq: e.icmp_seq,
        rtt_ms: e.rtt_ms,
        timestamp: e.timestamp,
        endpoint: json.data.endpoint_id,
        raw_output: e.raw_output || '',
      }))
      set((state) => ({
        packetEvidenceTimeline: {
          ...state.packetEvidenceTimeline,
          [endpointId]: records.slice(-30),
        },
      }))
    } catch {
      // backend may not be ready
    }
  },
}))

export default useMetricsStore
