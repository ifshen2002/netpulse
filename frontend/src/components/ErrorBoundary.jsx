import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Write error to both console and DOM so it's visible even if React crashes
    console.error('ErrorBoundary caught:', error, info)
    if (typeof window !== 'undefined' && window.__npErrors) {
      window.__npErrors.push('React Error: ' + (error.message || error))
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          padding: 16,
          background: '#1a0000',
          border: '1px solid var(--red)',
          borderRadius: 6,
          color: 'var(--red)',
          fontSize: 13,
          fontFamily: 'monospace',
        }}>
          <p style={{ fontWeight: 600, margin: '0 0 8px' }}>{this.props.fallback || 'Component unavailable'}</p>
          <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 11, opacity: 0.8 }}>
            {this.state.error.message || String(this.state.error)}
          </pre>
        </div>
      )
    }
    return this.props.children
  }
}
