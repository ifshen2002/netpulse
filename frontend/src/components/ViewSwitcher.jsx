import useMetricsStore from '../store/metricsStore'

export default function ViewSwitcher() {
  const activeView = useMetricsStore((s) => s.activeView)
  const setActiveView = useMetricsStore((s) => s.setActiveView)

  const views = [
    { key: 'link', label: 'Link View' },
    { key: 'node', label: 'Node View' },
  ]

  return (
    <div className="flex items-center rounded border" style={{ borderColor: 'var(--border)', overflow: 'hidden' }}>
      {views.map((v) => {
        const active = activeView === v.key
        return (
          <button
            key={v.key}
            onClick={() => setActiveView(v.key)}
            className="px-2.5 py-0.5 text-xs font-semibold transition-colors"
            style={{
              background: active ? 'var(--accent-bg)' : 'transparent',
              color: active ? 'var(--accent)' : 'var(--gray)',
              border: 'none',
              cursor: 'pointer',
              fontSize: 11,
            }}
          >
            {v.label}
          </button>
        )
      })}
    </div>
  )
}
