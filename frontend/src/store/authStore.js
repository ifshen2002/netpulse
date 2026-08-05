import '../lib/api'
import { create } from 'zustand'

const STORAGE_KEY = 'netpulse.session'

function readSession() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
  } catch {
    return null
  }
}

const useAuthStore = create((set, get) => ({
  session: readSession(),
  initialized: false,
  error: '',
  projectRole: null,  // viewer | editor | platform_admin | null (not loaded)

  initialize: async () => {
    const session = readSession()
    if (!session?.access_token) {
      set({ session: null, initialized: true })
      return
    }
    try {
      const response = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
      const json = await response.json()
      if (!json.success) throw new Error('session expired')
      const next = { ...session, user: json.data }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      set({ session: next, initialized: true, error: '' })
      // Fetch project role after session is verified
      get().fetchProjectRole()
    } catch {
      localStorage.removeItem(STORAGE_KEY)
      localStorage.removeItem('netpulse.project')
      set({ session: null, initialized: true })
    }
  },

  authenticate: async (mode, payload) => {
    set({ error: '' })
    try {
      const response = await fetch(`/api/auth/${mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const json = await response.json()
      if (!response.ok || !json.success) {
        throw new Error(json.detail || json.error?.message || 'Authentication failed')
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(json.data))
      set({ session: json.data, error: '' })
      get().fetchProjectRole()
      return true
    } catch (error) {
      set({ error: error.message || 'Authentication failed' })
      return false
    }
  },

  logout: async () => {
    const session = readSession()
    try {
      if (session?.access_token) {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: { Authorization: `Bearer ${session.access_token}` },
        })
      }
    } finally {
      localStorage.removeItem(STORAGE_KEY)
      set({ session: null, error: '', projectRole: null })
    }
  },

  fetchProjectRole: async () => {
    const { session } = get()
    if (!session?.access_token) return
    try {
      const { getProjectId } = await import('../lib/api')
      const projectId = getProjectId()
      const resp = await fetch('/api/projects', {
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
      const json = await resp.json()
      if (!json.success) return
      const projects = json.data || []
      if (session.user?.is_platform_admin) {
        set({ projectRole: 'platform_admin' })
        return
      }
      if (projectId) {
        const match = projects.find((p) => p.id === projectId)
        set({ projectRole: match?.role || null })
      } else if (projects.length === 1) {
        set({ projectRole: projects[0].role })
        const { setProjectId } = await import('../lib/api')
        setProjectId(projects[0].id)
      }
    } catch {
      // no-op
    }
  },
}))

export default useAuthStore
