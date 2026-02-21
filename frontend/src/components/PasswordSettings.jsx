import { useEffect, useState } from 'react'
import axios from 'axios'
import { applyTheme, getStoredTheme } from '../utils/theme'

export default function PasswordSettings({ authHeaders, onSessionUpdate }) {
  const [theme, setTheme] = useState('light')
  const [form, setForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [themeMessage, setThemeMessage] = useState(null)

  const headers = authHeaders || {}

  useEffect(() => {
    setTheme(getStoredTheme())
  }, [])

  const updateTheme = (nextTheme) => {
    const applied = applyTheme(nextTheme)
    setTheme(applied)
    setThemeMessage(`Theme updated to ${applied === 'dark' ? 'Dark' : 'Light'} mode`)
  }

  const submit = async (e) => {
    e.preventDefault()
    setMessage(null)

    if (form.new_password.length < 8) {
      setMessage({ type: 'error', text: 'New password must be at least 8 characters' })
      return
    }
    if (form.new_password !== form.confirm_password) {
      setMessage({ type: 'error', text: 'New password and confirm password do not match' })
      return
    }

    setSaving(true)
    try {
      const res = await axios.put('/api/admin/auth/password', {
        current_password: form.current_password,
        new_password: form.new_password,
      }, { headers })
      setForm({ current_password: '', new_password: '', confirm_password: '' })
      setMessage({ type: 'success', text: 'Password updated successfully' })
      if (res.data?.session_token && onSessionUpdate) {
        onSessionUpdate(res.data.session_token)
      }
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to update password'
      setMessage({ type: 'error', text: detail })
    } finally {
      setSaving(false)
    }
  }

  const inputStyle = {
    width: '100%',
    padding: '10px 12px',
    borderRadius: '8px',
    border: '1px solid var(--border)',
    fontSize: '14px',
    outline: 'none',
    background: 'var(--bg)',
    color: 'var(--text)',
  }

  const labelStyle = {
    display: 'block',
    fontSize: '13px',
    fontWeight: 500,
    marginBottom: '4px',
    color: 'var(--text)',
  }

  return (
    <div style={{
      background: 'var(--surface)',
      borderRadius: '12px',
      border: '1px solid var(--border)',
      padding: '24px',
    }}>
      <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>
        Settings
      </h2>

      <div style={{
        marginBottom: '20px',
        padding: '12px',
        borderRadius: '8px',
        border: '1px solid var(--border)',
        background: 'var(--bg)',
      }}>
        <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>
          Appearance
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            onClick={() => updateTheme('light')}
            style={{
              padding: '8px 14px',
              borderRadius: '8px',
              border: `1px solid ${theme === 'light' ? 'var(--primary)' : 'var(--border)'}`,
              background: theme === 'light' ? 'var(--primary-light)' : 'var(--surface)',
              color: theme === 'light' ? 'var(--primary)' : 'var(--text)',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            Light
          </button>
          <button
            type="button"
            onClick={() => updateTheme('dark')}
            style={{
              padding: '8px 14px',
              borderRadius: '8px',
              border: `1px solid ${theme === 'dark' ? 'var(--primary)' : 'var(--border)'}`,
              background: theme === 'dark' ? 'var(--primary-light)' : 'var(--surface)',
              color: theme === 'dark' ? 'var(--primary)' : 'var(--text)',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            Dark
          </button>
        </div>
        {themeMessage && (
          <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--text-secondary)' }}>
            {themeMessage}
          </div>
        )}
      </div>

      <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px' }}>
        Password Settings
      </h3>

      <form onSubmit={submit}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div>
            <label style={labelStyle}>Current Password</label>
            <input
              style={inputStyle}
              type="password"
              value={form.current_password}
              onChange={e => setForm({ ...form, current_password: e.target.value })}
              autoComplete="current-password"
            />
          </div>
          <div>
            <label style={labelStyle}>New Password</label>
            <input
              style={inputStyle}
              type="password"
              value={form.new_password}
              onChange={e => setForm({ ...form, new_password: e.target.value })}
              autoComplete="new-password"
            />
          </div>
          <div>
            <label style={labelStyle}>Confirm New Password</label>
            <input
              style={inputStyle}
              type="password"
              value={form.confirm_password}
              onChange={e => setForm({ ...form, confirm_password: e.target.value })}
              autoComplete="new-password"
            />
          </div>
        </div>

        {message && (
          <div style={{
            marginTop: '12px',
            padding: '8px 12px',
            borderRadius: '8px',
            fontSize: '13px',
            background: message.type === 'error' ? 'var(--status-error-bg)' : 'var(--status-success-bg)',
            border: `1px solid ${message.type === 'error' ? 'var(--status-error-border)' : 'var(--status-success-border)'}`,
            color: message.type === 'error' ? 'var(--error)' : 'var(--success)',
          }}>
            {message.text}
          </div>
        )}

        <button
          type="submit"
          disabled={saving}
          style={{
            marginTop: '12px',
            padding: '10px 20px',
            borderRadius: '8px',
            border: 'none',
            background: 'var(--primary)',
            color: 'var(--on-primary)',
            fontSize: '14px',
            fontWeight: 500,
            opacity: saving ? 0.6 : 1,
          }}
        >
          {saving ? 'Updating...' : 'Update Password'}
        </button>
      </form>
    </div>
  )
}
