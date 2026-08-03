import { useEffect, useState } from 'react'
import { apiJson, getProjectId, setProjectId } from '../lib/api'

export default function ProjectSelector() {
  const [projects, setProjects] = useState([])
  const [current, setCurrent] = useState(() => getProjectId() || '')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const resp = await apiJson('/api/projects')
        if (!cancelled) {
          setProjects(resp.data || [])
          const saved = getProjectId()
          // Validate saved project_id still exists; if not, pick the first one.
          const valid = saved && resp.data?.some((p) => p.id === saved)
          if (!valid && resp.data?.length) {
            setCurrent(resp.data[0].id)
            setProjectId(resp.data[0].id)
          } else if (valid) {
            setCurrent(saved)
          }
        }
      } catch {
        // backend may not be ready
      }
    })()
    return () => { cancelled = true }
  }, [])

  if (projects.length <= 1) return null

  return (
    <select
      value={current}
      onChange={(e) => {
        setCurrent(e.target.value)
        setProjectId(e.target.value)
        window.location.reload()
      }}
      className="rounded px-2 py-1 text-xs"
      style={{
        background: 'var(--bg)',
        border: '1px solid var(--border)',
        color: 'var(--text-h)',
        cursor: 'pointer',
        maxWidth: 200,
      }}
    >
      {projects.map((p) => (
        <option key={p.id} value={p.id}>
          {p.organization_name} / {p.name} {p.role ? `(${p.role})` : ''}
        </option>
      ))}
    </select>
  )
}
