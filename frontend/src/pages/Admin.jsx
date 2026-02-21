import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import LLMConfig from '../components/LLMConfig'
import FileManager from '../components/FileManager'
import ImageManager from '../components/ImageManager'
import VideoLinks from '../components/VideoLinks'
import PasswordSettings from '../components/PasswordSettings'

const ADMIN_SESSION_STORAGE_KEY = 'adminSessionToken'

function SectionIcon({ id }) {
  const iconProps = {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    width: 18,
    height: 18,
    'aria-hidden': true,
  }

  switch (id) {
    case 'documents':
      return (
        <svg {...iconProps}>
          <path d="M7 3h7l5 5v13H7z" />
          <path d="M14 3v5h5" />
          <path d="M9 13h8M9 17h6" />
        </svg>
      )
    case 'images':
      return (
        <svg {...iconProps}>
          <rect x="3" y="4" width="18" height="16" rx="3" />
          <circle cx="9" cy="10" r="1.6" />
          <path d="M5 17l4-4 3 3 4-5 3 4" />
        </svg>
      )
    case 'videos':
      return (
        <svg {...iconProps}>
          <rect x="3" y="5" width="18" height="14" rx="3" />
          <path d="M10 10l6 4-6 4z" />
        </svg>
      )
    case 'settings':
      return (
        <svg {...iconProps}>
          <circle cx="12" cy="12" r="3.5" />
          <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.2 2.2M16.2 16.2l2.2 2.2M18.4 5.6l-2.2 2.2M7.8 16.2l-2.2 2.2" />
        </svg>
      )
    case 'llm':
    default:
      return (
        <svg {...iconProps}>
          <rect x="3" y="3" width="18" height="18" rx="4" />
          <path d="M8 9h8M8 12h8M8 15h5" />
        </svg>
      )
  }
}

export default function Admin() {
  const [password, setPassword] = useState('')
  const [sessionToken, setSessionToken] = useState('')
  const [authenticated, setAuthenticated] = useState(false)
  const [authError, setAuthError] = useState('')
  const [authChecking, setAuthChecking] = useState(true)
  const [authLoading, setAuthLoading] = useState(false)
  const [activeSection, setActiveSection] = useState('llm')
  const [isNavigatorCollapsed, setIsNavigatorCollapsed] = useState(false)

  const authHeaders = sessionToken ? { 'X-Admin-Session': sessionToken } : {}

  const applySession = (token) => {
    setSessionToken(token)
    setAuthenticated(true)
    localStorage.setItem(ADMIN_SESSION_STORAGE_KEY, token)
  }

  const clearSession = () => {
    setSessionToken('')
    setAuthenticated(false)
    localStorage.removeItem(ADMIN_SESSION_STORAGE_KEY)
  }

  const validateSession = async (token) => {
    try {
      const res = await fetch('/api/admin/auth/session', {
        headers: { 'X-Admin-Session': token },
      })
      return res.ok
    } catch {
      return false
    }
  }

  useEffect(() => {
    const boot = async () => {
      const storedToken = localStorage.getItem(ADMIN_SESSION_STORAGE_KEY)
      if (!storedToken) {
        setAuthChecking(false)
        return
      }

      const valid = await validateSession(storedToken)
      if (valid) {
        setSessionToken(storedToken)
        setAuthenticated(true)
      } else {
        localStorage.removeItem(ADMIN_SESSION_STORAGE_KEY)
      }
      setAuthChecking(false)
    }

    boot()
  }, [])

  const handleLogin = async (e) => {
    e.preventDefault()
    setAuthError('')
    setAuthLoading(true)

    try {
      const res = await fetch('/api/admin/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setAuthError(body.detail || 'Invalid password')
        setAuthLoading(false)
        return
      }
      const data = await res.json()
      applySession(data.session_token)
      setPassword('')
    } catch {
      setAuthError('Login failed')
    } finally {
      setAuthLoading(false)
    }
  }

  const handleLogout = async () => {
    try {
      if (sessionToken) {
        await fetch('/api/admin/auth/logout', {
          method: 'POST',
          headers: { 'X-Admin-Session': sessionToken },
        })
      }
    } catch {
      // Logout should clear local session even if request fails
    } finally {
      clearSession()
      setPassword('')
    }
  }

  if (authChecking) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        background: 'var(--bg)',
        color: 'var(--text-secondary)',
        fontSize: '14px',
      }}>
        Checking session...
      </div>
    )
  }

  if (!authenticated) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        background: 'var(--bg)',
        padding: '20px',
      }}>
        <div style={{
          background: 'var(--surface)',
          borderRadius: '16px',
          border: '1px solid var(--border)',
          padding: '40px',
          width: '100%',
          maxWidth: '400px',
          textAlign: 'center',
        }}>
          <img src="/logo.png" alt="Quilr AI" style={{ height: '48px', marginBottom: '16px' }} />
          <h1 style={{ fontSize: '20px', fontWeight: 600, marginBottom: '8px' }}>
            Admin Console
          </h1>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '24px' }}>
            Enter the admin password to continue
          </p>

          <form onSubmit={handleLogin}>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Admin password"
              autoFocus
              style={{
                width: '100%',
                padding: '12px 16px',
                borderRadius: '10px',
                border: `1px solid ${authError ? 'var(--error)' : 'var(--border)'}`,
                fontSize: '14px',
                outline: 'none',
                background: 'var(--bg)',
                marginBottom: '12px',
              }}
            />
            {authError && (
              <p style={{ fontSize: '13px', color: 'var(--error)', marginBottom: '12px' }}>
                {authError}
              </p>
            )}
            <button
              type="submit"
              disabled={authLoading}
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '10px',
                border: 'none',
                background: 'var(--primary)',
                color: 'var(--on-primary)',
                fontSize: '14px',
                fontWeight: 500,
                opacity: authLoading ? 0.6 : 1,
              }}
            >
              {authLoading ? 'Signing In...' : 'Sign In'}
            </button>
          </form>

          <Link to="/" style={{
            display: 'inline-block',
            marginTop: '16px',
            fontSize: '13px',
            color: 'var(--text-secondary)',
            textDecoration: 'none',
          }}>
            Back to Chat
          </Link>
        </div>
      </div>
    )
  }

  const sections = [
    {
      id: 'llm',
      label: 'LLM Configuration',
      description: 'Provider, model, and connection settings',
    },
    {
      id: 'documents',
      label: 'Documents',
      description: 'Upload, index, and manage PDF docs',
    },
    {
      id: 'images',
      label: 'Images',
      description: 'Upload screenshots and describe them',
    },
    {
      id: 'videos',
      label: 'Videos',
      description: 'Manage demo links, uploads, and transcripts',
    },
    {
      id: 'settings',
      label: 'Settings',
      description: 'Manage security and admin password',
    },
  ]

  const activeMeta = sections.find(section => section.id === activeSection)

  const renderActiveSection = () => {
    switch (activeSection) {
      case 'documents':
        return <FileManager authHeaders={authHeaders} />
      case 'images':
        return <ImageManager authHeaders={authHeaders} />
      case 'videos':
        return <VideoLinks authHeaders={authHeaders} />
      case 'settings':
        return <PasswordSettings authHeaders={authHeaders} onSessionUpdate={applySession} />
      case 'llm':
      default:
        return <LLMConfig authHeaders={authHeaders} />
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg)',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 20px',
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <img src="/logo.png" alt="Quilr AI" style={{ height: '36px' }} />
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: 600 }}>Admin Console</h1>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Manage LLM settings, content, and security
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={handleLogout}
            style={{
              fontSize: '13px',
              color: 'var(--text-secondary)',
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
            }}
          >
            Sign Out
          </button>
          <Link to="/" style={{
            fontSize: '13px',
            color: 'var(--text-secondary)',
            textDecoration: 'none',
            padding: '6px 12px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
          }}>
            Back to Chat
          </Link>
        </div>
      </div>

      <div className="admin-fullscreen">
        <div className={`admin-layout ${isNavigatorCollapsed ? 'sidebar-collapsed' : ''}`}>
          <aside className={`admin-sidebar ${isNavigatorCollapsed ? 'collapsed' : ''}`}>
            <div className="admin-sidebar-header">
              <div className="admin-sidebar-title">Navigator</div>
              <button
                type="button"
                className="admin-sidebar-toggle"
                onClick={() => setIsNavigatorCollapsed(prev => !prev)}
                aria-label={isNavigatorCollapsed ? 'Expand navigator' : 'Collapse navigator'}
                title={isNavigatorCollapsed ? 'Expand navigator' : 'Collapse navigator'}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  width="16"
                  height="16"
                  aria-hidden="true"
                >
                  {isNavigatorCollapsed ? (
                    <path d="M9 6l6 6-6 6" />
                  ) : (
                    <path d="M15 6l-6 6 6 6" />
                  )}
                </svg>
              </button>
            </div>
            <div className="admin-nav-list">
              {sections.map((section) => {
                const active = activeSection === section.id
                return (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    className={`admin-nav-btn ${active ? 'active' : ''}`}
                    title={isNavigatorCollapsed ? section.label : undefined}
                  >
                    <div className="admin-nav-icon">
                      <SectionIcon id={section.id} />
                    </div>
                    <div className="admin-nav-copy">
                      <div className="admin-nav-title">{section.label}</div>
                      <div className="admin-nav-description">{section.description}</div>
                    </div>
                  </button>
                )
              })}
            </div>
          </aside>

          <div className="admin-panel">
            <div style={{ marginBottom: '14px' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 600 }}>
                {activeMeta?.label}
              </h2>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                {activeMeta?.description}
              </p>
            </div>
            {renderActiveSection()}
          </div>
        </div>
      </div>
    </div>
  )
}
