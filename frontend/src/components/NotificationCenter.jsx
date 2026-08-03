import { useEffect, useState } from 'react'
import useMetricsStore from '../store/metricsStore'

export default function NotificationCenter() {
  const notifications = useMetricsStore((s) => s.notifications)
  const unreadCount = useMetricsStore((s) => s.unreadCount)
  const fetchNotifications = useMetricsStore((s) => s.fetchNotifications)
  const markRead = useMetricsStore((s) => s.markNotificationRead)
  const acknowledge = useMetricsStore((s) => s.acknowledgeNotification)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    fetchNotifications()
    const interval = setInterval(fetchNotifications, 30000)
    return () => clearInterval(interval)
  }, [fetchNotifications])

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="relative rounded px-2 py-1 text-xs flex items-center gap-1"
        style={{
          background: 'transparent',
          border: '1px solid var(--border)',
          color: 'var(--gray)',
          cursor: 'pointer',
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unreadCount > 0 && (
          <span
            className="absolute -top-1 -right-1 rounded-full text-xs flex items-center justify-center"
            style={{
              width: 16,
              height: 16,
              background: 'var(--red)',
              color: '#fff',
              fontSize: 9,
              fontWeight: 700,
            }}
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="absolute right-0 top-full mt-1 z-50 rounded-lg p-1 w-80"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', boxShadow: '0 4px 24px rgba(0,0,0,0.4)' }}
          >
            <div className="flex items-center justify-between px-3 py-2 border-b" style={{ borderColor: 'var(--border)' }}>
              <span className="text-sm font-semibold">Notifications</span>
              <span className="text-xs" style={{ color: 'var(--gray)' }}>
                {unreadCount} unread
              </span>
            </div>
            <div className="max-h-80 overflow-y-auto">
              {notifications.length === 0 ? (
                <p className="text-xs px-3 py-4 text-center" style={{ color: 'var(--gray)' }}>
                  No notifications yet.
                </p>
              ) : (
                notifications.map((n) => (
                  <div
                    key={n.id}
                    className="px-3 py-2 text-xs border-b flex flex-col gap-1"
                    style={{
                      borderColor: 'var(--border)',
                      background: n.status === 'unread' ? 'var(--accent-bg)' : 'transparent',
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <span
                        className="rounded px-1.5 py-0.5 text-xs font-semibold"
                        style={{
                          background: n.severity === 'critical' ? 'var(--red)' : 'var(--yellow)',
                          color: '#fff',
                          fontSize: 9,
                        }}
                      >
                        {n.severity}
                      </span>
                      <span style={{ color: 'var(--gray)', fontSize: 9 }}>
                        {n.created_at ? new Date(n.created_at).toLocaleTimeString() : ''}
                      </span>
                    </div>
                    <div style={{ color: 'var(--text-h)' }}>{n.title}</div>
                    {n.body && <div style={{ color: 'var(--gray)' }}>{n.body}</div>}
                    <div className="flex gap-2 mt-1">
                      {n.status === 'unread' && (
                        <button
                          type="button"
                          onClick={() => markRead(n.id)}
                          className="rounded px-1.5 py-0.5"
                          style={{
                            background: 'transparent',
                            border: '1px solid var(--border)',
                            color: 'var(--accent)',
                            cursor: 'pointer',
                            fontSize: 10,
                          }}
                        >
                          Mark read
                        </button>
                      )}
                      {n.status !== 'acknowledged' && n.status !== 'resolved' && (
                        <button
                          type="button"
                          onClick={() => acknowledge(n.id)}
                          className="rounded px-1.5 py-0.5"
                          style={{
                            background: 'transparent',
                            border: '1px solid var(--border)',
                            color: 'var(--gray)',
                            cursor: 'pointer',
                            fontSize: 10,
                          }}
                        >
                          Acknowledge
                        </button>
                      )}
                      {n.status === 'acknowledged' && (
                        <span style={{ color: 'var(--green)', fontSize: 10 }}>Acknowledged</span>
                      )}
                      {n.status === 'resolved' && (
                        <span style={{ color: 'var(--gray)', fontSize: 10 }}>Resolved</span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
