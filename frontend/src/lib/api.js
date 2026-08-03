const STORAGE_KEY = 'netpulse.session'
const PROJECT_KEY = 'netpulse.project'
const ORIGINAL_FETCH = globalThis.fetch?.bind(globalThis)

if (ORIGINAL_FETCH && !globalThis.__netpulseAuthFetchInstalled) {
  globalThis.__netpulseAuthFetchInstalled = true
  globalThis.fetch = async (input, init = {}) => {
    const request = typeof input === 'string' ? input : input?.url || ''
    const headers = new Headers(init.headers || input?.headers || {})
    const token = getAccessToken()
    if (token && request.startsWith('/api/') && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    const projectId = getProjectId()
    if (projectId && request.startsWith('/api/') && !headers.has('X-Project-ID')) {
      headers.set('X-Project-ID', projectId)
    }
    return ORIGINAL_FETCH(input, { ...init, headers })
  }
}

function readSession() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
  } catch {
    return null
  }
}

export function getAccessToken() {
  return readSession()?.access_token || null
}

export function getProjectId() {
  return localStorage.getItem(PROJECT_KEY) || null
}

export function setProjectId(projectId) {
  if (projectId) localStorage.setItem(PROJECT_KEY, projectId)
  else localStorage.removeItem(PROJECT_KEY)
}

export async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {})
  const token = getAccessToken()
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const projectId = getProjectId()
  if (projectId && !headers.has('X-Project-ID')) headers.set('X-Project-ID', projectId)
  if (options.body && !headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  return fetch(path, { ...options, headers })
}

export async function apiJson(path, options = {}) {
  const response = await apiFetch(path, options)
  const json = await response.json()
  if (!response.ok || json.success === false) {
    throw new Error(json.detail || json.error?.message || 'Request failed')
  }
  return json
}
