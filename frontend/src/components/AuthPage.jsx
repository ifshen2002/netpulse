import { useState } from 'react'
import useAuthStore from '../store/authStore'

export default function AuthPage() {
  const authenticate = useAuthStore((s) => s.authenticate)
  const error = useAuthStore((s) => s.error)
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    const payload = { email, password }
    if (mode === 'register') payload.display_name = displayName
    await authenticate(mode, payload)
    setSubmitting(false)
  }

  const inputStyle = {
    background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-h)', outline: 'none',
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-4" style={{ background: 'var(--bg)' }}>
      <form onSubmit={submit} className="rounded-lg p-6 flex flex-col gap-4 w-full" style={{ maxWidth: 380, background: 'var(--bg-card)', border: '1px solid var(--border)' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24 }}>NetPulse</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--gray)' }}>Production observability platform</p>
        </div>
        {mode === 'register' && (
          <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
            Display name
            <input required value={displayName} onChange={(e) => setDisplayName(e.target.value)} className="rounded px-3 py-2 text-sm" style={inputStyle} />
          </label>
        )}
        <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
          Email
          <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="rounded px-3 py-2 text-sm" style={inputStyle} />
        </label>
        <label className="flex flex-col gap-1 text-xs" style={{ color: 'var(--gray)' }}>
          Password
          <input required minLength={mode === 'register' ? 12 : 1} type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="rounded px-3 py-2 text-sm" style={inputStyle} />
        </label>
        {error && <p className="text-xs" style={{ color: 'var(--red)' }}>{error}</p>}
        <button disabled={submitting} className="rounded px-3 py-2 text-sm font-semibold" style={{ background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', opacity: submitting ? 0.65 : 1 }}>
          {submitting ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
        </button>
        <button type="button" onClick={() => setMode(mode === 'login' ? 'register' : 'login')} className="text-xs" style={{ color: 'var(--accent)', background: 'transparent', border: 'none', cursor: 'pointer' }}>
          {mode === 'login' ? 'Need an account? Register' : 'Already have an account? Sign in'}
        </button>
      </form>
    </main>
  )
}
