import { useEffect, useState } from 'react'
import axios from 'axios'
import { showToast } from '../utils/toast'

export default function PasswordSettings({ authHeaders, onSessionUpdate, canChangePassword = true }) {
  const [form, setForm] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [accessRows, setAccessRows] = useState([])
  const [accessEmail, setAccessEmail] = useState('')
  const [accessLoading, setAccessLoading] = useState(false)
  const [accessMessage, setAccessMessage] = useState(null)

  const headers = authHeaders || {}
  const sessionToken = headers['X-Admin-Session'] || ''

  useEffect(() => {
    if (!message?.text) return
    showToast(message)
    setMessage(null)
  }, [message])

  useEffect(() => {
    if (!accessMessage?.text) return
    showToast(accessMessage)
    setAccessMessage(null)
  }, [accessMessage])

  const loadAccessList = async () => {
    try {
      const res = await axios.get('/api/admin/auth/oauth-access', { headers })
      setAccessRows(res.data?.emails || [])
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to load admin email access list'
      setAccessMessage({ type: 'error', text: detail })
    }
  }

  useEffect(() => {
    loadAccessList()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionToken])

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

  const addAccessEmail = async () => {
    const email = accessEmail.trim().toLowerCase()
    if (!email) {
      setAccessMessage({ type: 'error', text: 'Enter an email address' })
      return
    }

    setAccessLoading(true)
    setAccessMessage(null)
    try {
      await axios.post('/api/admin/auth/oauth-access', { email }, { headers })
      setAccessEmail('')
      setAccessMessage({ type: 'success', text: 'Email added to admin access list' })
      await loadAccessList()
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to add email'
      setAccessMessage({ type: 'error', text: detail })
    } finally {
      setAccessLoading(false)
    }
  }

  const removeAccessEmail = async (email) => {
    setAccessLoading(true)
    setAccessMessage(null)
    try {
      await axios.delete('/api/admin/auth/oauth-access', {
        headers,
        params: { email },
      })
      setAccessMessage({ type: 'success', text: 'Email removed from admin access list' })
      await loadAccessList()
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to remove email'
      setAccessMessage({ type: 'error', text: detail })
    } finally {
      setAccessLoading(false)
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
        Security
      </h2>

      <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '12px' }}>
        Password Settings
      </h3>

      {canChangePassword ? (
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
      ) : (
        <div style={{
          padding: '10px 12px',
          borderRadius: '8px',
          border: '1px solid var(--border)',
          background: 'var(--bg)',
          fontSize: '12px',
          color: 'var(--text-secondary)',
        }}>
          Password change is restricted to main admin password login only.
        </div>
      )}

      <div style={{
        marginTop: '20px',
        paddingTop: '16px',
        borderTop: '1px solid var(--border)',
      }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '8px' }}>
          OAuth Admin Email Access
        </h3>
        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '10px' }}>
          Only these email IDs can enter Admin using Microsoft/Google sign-in.
        </p>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            style={inputStyle}
            type="email"
            value={accessEmail}
            onChange={e => setAccessEmail(e.target.value)}
            placeholder="name@company.com"
          />
          <button
            type="button"
            onClick={addAccessEmail}
            disabled={accessLoading}
            style={{
              padding: '10px 14px',
              borderRadius: '8px',
              border: 'none',
              background: 'var(--primary)',
              color: 'var(--on-primary)',
              fontSize: '13px',
              fontWeight: 500,
              opacity: accessLoading ? 0.6 : 1,
              whiteSpace: 'nowrap',
            }}
          >
            Add Email
          </button>
        </div>

        <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {accessRows.length === 0 && (
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              No emails added yet.
            </div>
          )}
          {accessRows.map((row) => (
            <div
              key={row.email}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                border: '1px solid var(--border)',
                borderRadius: '8px',
                padding: '8px 10px',
                background: 'var(--bg)',
              }}
            >
              <div style={{ fontSize: '13px', color: 'var(--text)' }}>{row.email}</div>
              <button
                type="button"
                onClick={() => removeAccessEmail(row.email)}
                disabled={accessLoading}
                style={{
                  padding: '6px 10px',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  background: 'var(--surface)',
                  color: 'var(--text-secondary)',
                  fontSize: '12px',
                }}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
