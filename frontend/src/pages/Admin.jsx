import { useState } from 'react'
import { Link } from 'react-router-dom'
import LLMConfig from '../components/LLMConfig'
import FileManager from '../components/FileManager'
import VideoLinks from '../components/VideoLinks'

export default function Admin() {
  const [password, setPassword] = useState('')
  const [authenticated, setAuthenticated] = useState(false)
  const [authError, setAuthError] = useState(false)

  const handleLogin = async (e) => {
    e.preventDefault()
    setAuthError(false)

    // Validate by trying to fetch config
    try {
      const res = await fetch('/api/admin/config', {
        headers: { 'X-Admin-Password': password },
      })
      if (res.ok) {
        setAuthenticated(true)
      } else {
        setAuthError(true)
      }
    } catch {
      setAuthError(true)
    }
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
                Invalid password
              </p>
            )}
            <button
              type="submit"
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: '10px',
                border: 'none',
                background: 'var(--primary)',
                color: '#fff',
                fontSize: '14px',
                fontWeight: 500,
              }}
            >
              Sign In
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

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg)',
    }}>
      {/* Header */}
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
              Manage LLM settings and documents
            </p>
          </div>
        </div>
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

      {/* Content */}
      <div style={{
        maxWidth: '800px',
        margin: '0 auto',
        padding: '24px 20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px',
      }}>
        <LLMConfig password={password} />
        <FileManager password={password} />
        <VideoLinks password={password} />
      </div>
    </div>
  )
}
