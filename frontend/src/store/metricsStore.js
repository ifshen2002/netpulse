import { create } from 'zustand'

const useMetricsStore = create((set) => ({
  metrics: {},
  connected: false,

  updateMetric: (event) =>
    set((state) => ({
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
    })),

  setConnected: (value) => set({ connected: value }),
}))

export default useMetricsStore
