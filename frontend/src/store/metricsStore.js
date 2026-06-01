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
          probe_id: event.probe_id,
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
          probe_id: event.probe_id,
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

  // ── V2 probe state ─────────────────────────────────────────
  probeMetrics: {},
  probeHistory: {},
  packetEvidence: {},
  packetEvidenceTimeline: {},   // { [probe_id]: [...recent records] }
  linkStatuses: {},
  activeView: 'link',
  visibleProbes: {},

  // ── V2 network chaos ──────────────────────────────────────
  networkChaos: null,
  lastChaosSession: null,

  setNetworkChaos: (data) =>
    set((state) => {
      // When chaos clears, capture the session for the last-chaos summary
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

  updateProbeMetric: (event) =>
    set((state) => {
      const point = {
        timestamp: event.timestamp,
        latency_ms: event.latency_ms,
        packet_loss_pct: event.packet_loss_pct,
        availability_pct: event.availability_pct,
      }
      const prev = state.probeHistory[event.probe_id] || []
      const next = [...prev, point]
      if (next.length > MAX_HISTORY) next.splice(0, next.length - MAX_HISTORY)

      const nextVP = { ...state.visibleProbes }
      if (!(event.probe_id in nextVP)) nextVP[event.probe_id] = true

      return {
        probeMetrics: {
          ...state.probeMetrics,
          [event.probe_id]: {
            latency_ms: event.latency_ms,
            packet_loss_pct: event.packet_loss_pct,
            availability_pct: event.availability_pct,
            status: event.status,
            endpoint: event.endpoint,
            link_id: event.link_id,
            timestamp: event.timestamp,
          },
        },
        probeHistory: {
          ...state.probeHistory,
          [event.probe_id]: next,
        },
        visibleProbes: nextVP,
      }
    }),

  updatePacketEvidence: (event) =>
    set((state) => {
      // Auto-register probe visibility when evidence arrives via WebSocket.
      // This handles the case where fetchInitialProbes failed on WS open
      // (e.g. DB not ready) but evidence later flows through push events.
      const nextVP = { ...state.visibleProbes }
      if (!(event.probe_id in nextVP)) nextVP[event.probe_id] = true
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
        link_id: event.link_id,
        endpoint: event.endpoint,
        raw_output: event.raw_output || '',
      }
      // Accumulate evidence timeline — keep last 30 records per probe
      const prevTimeline = state.packetEvidenceTimeline[event.probe_id] || []
      const nextTimeline = [...prevTimeline, record]
      if (nextTimeline.length > 30) nextTimeline.splice(0, nextTimeline.length - 30)

      return {
        packetEvidence: {
          ...state.packetEvidence,
          [event.probe_id]: record,
        },
        packetEvidenceTimeline: {
          ...state.packetEvidenceTimeline,
          [event.probe_id]: nextTimeline,
        },
        visibleProbes: nextVP,
      }
    }),

  updateLinkStatus: (event) =>
    set((state) => {
      const probeId = event.probe_id
      const existing = state.probeMetrics[probeId]
      // Also update the probe metric status if it exists
      const nextMetrics = existing
        ? { ...state.probeMetrics, [probeId]: { ...existing, status: event.status } }
        : state.probeMetrics
      return {
        linkStatuses: { ...state.linkStatuses, [event.link_id]: event.status },
        probeMetrics: nextMetrics,
      }
    }),

  setActiveView: (view) => set({ activeView: view }),

  toggleProbeVisibility: (probeId) =>
    set((state) => ({
      visibleProbes: {
        ...state.visibleProbes,
        [probeId]: !state.visibleProbes[probeId],
      },
    })),

  fetchInitialProbes: async () => {
    try {
      const resp = await fetch('/api/probes')
      const json = await resp.json()
      if (!json.success) return
      const probes = json.data.probes || []
      const windowS = json.data.window_s || 30

      // Seed visibleProbes
      set((state) => {
        const next = { ...state.visibleProbes }
        for (const p of probes) {
          if (!(p.id in next)) next[p.id] = true
        }
        return { visibleProbes: next }
      })

      // Fetch initial metrics for each probe
      for (const p of probes) {
        try {
          const mResp = await fetch(`/api/probes/${p.id}/metrics?seconds=${Math.max(windowS * 2, 60)}`)
          const mJson = await mResp.json()
          if (mJson.success && mJson.data.metrics.length > 0) {
            const points = mJson.data.metrics.reverse().map((d) => ({
              timestamp: d.timestamp,
              latency_ms: d.latency_ms,
              packet_loss_pct: d.packet_loss_pct,
              availability_pct: d.availability_pct,
            }))
            set((state) => ({
              probeHistory: {
                ...state.probeHistory,
                [p.id]: points.slice(-MAX_HISTORY),
              },
            }))
          }
        } catch {
          // probe may not have metrics yet
        }
      }

      // Fetch latest packet evidence for each probe
      for (const p of probes) {
        try {
          const eResp = await fetch(`/api/probes/${p.id}/evidence?limit=1`)
          const eJson = await eResp.json()
          if (eJson.success && eJson.data.evidence.length > 0) {
            const e = eJson.data.evidence[0]
            set((state) => ({
              packetEvidence: {
                ...state.packetEvidence,
                [p.id]: {
                  protocol: e.protocol,
                  src_ip: e.src_ip,
                  dst_ip: e.dst_ip,
                  ttl: e.ttl,
                  packet_size_bytes: e.packet_size_bytes,
                  icmp_seq: e.icmp_seq,
                  rtt_ms: e.rtt_ms,
                  timestamp: e.timestamp,
                  link_id: e.link_id,
                  endpoint: p.endpoint,
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

  fetchEvidenceTimeline: async (probeId, limit = 20) => {
    try {
      const resp = await fetch(`/api/probes/${probeId}/evidence?limit=${limit}`)
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
        link_id: e.link_id,
        endpoint: json.data.probe_id,
        raw_output: e.raw_output || '',
      }))
      set((state) => ({
        packetEvidenceTimeline: {
          ...state.packetEvidenceTimeline,
          [probeId]: records.slice(-30),
        },
      }))
    } catch {
      // backend may not be ready
    }
  },
}))

export default useMetricsStore
