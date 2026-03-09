import { useEffect, useState } from 'react'
import axios from 'axios'
import { showToast } from '../utils/toast'

function formatDate(iso) {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

export default function UsersActivity({ authHeaders }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [adminEmails, setAdminEmails] = useState([])
  const [updatingEmail, setUpdatingEmail] = useState('')

  const headers = authHeaders || {}

  const loadUsers = async (q = '') => {
    setLoading(true)
    try {
      const [usersRes, adminRes] = await Promise.all([
        axios.get('/api/admin/users/activity', {
          headers,
          params: { limit: 500, q: (q || '').trim().toLowerCase() },
        }),
        axios.get('/api/admin/auth/oauth-access', { headers }),
      ])
      setItems(usersRes.data?.items || [])
      const adminList = (adminRes.data?.emails || []).map(row => (row.email || '').trim().toLowerCase()).filter(Boolean)
      setAdminEmails(adminList)
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to load user activity'
      showToast({ type: 'error', text: detail })
    } finally {
      setLoading(false)
    }
  }

  const makeAdmin = async (email) => {
    const normalized = (email || '').trim().toLowerCase()
    if (!normalized) return
    setUpdatingEmail(normalized)
    try {
      await axios.post('/api/admin/auth/oauth-access', { email: normalized }, { headers })
      showToast({ type: 'success', text: `${normalized} added as admin` })
      await loadUsers(query)
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to add admin access'
      showToast({ type: 'error', text: detail })
    } finally {
      setUpdatingEmail('')
    }
  }

  const removeAdmin = async (email) => {
    const normalized = (email || '').trim().toLowerCase()
    if (!normalized) return
    setUpdatingEmail(normalized)
    try {
      await axios.delete('/api/admin/auth/oauth-access', {
        headers,
        params: { email: normalized },
      })
      showToast({ type: 'success', text: `${normalized} removed from admin` })
      await loadUsers(query)
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to remove admin access'
      showToast({ type: 'error', text: detail })
    } finally {
      setUpdatingEmail('')
    }
  }

  useEffect(() => {
    loadUsers()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div style={{
      background: 'var(--surface)',
      borderRadius: '12px',
      border: '1px solid var(--border)',
      padding: '24px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>Users</h2>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            Users who accessed the portal and can be used in Manage Access suggestions.
          </p>
        </div>
        <button
          type="button"
          onClick={() => loadUsers(query)}
          disabled={loading}
          style={{
            padding: '8px 12px',
            borderRadius: '8px',
            border: '1px solid var(--border)',
            background: 'var(--surface)',
            color: 'var(--text)',
            fontSize: '12px',
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
        <input
          type="email"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Filter by email"
          style={{
            flex: 1,
            padding: '8px 10px',
            borderRadius: '8px',
            border: '1px solid var(--border)',
            background: 'var(--bg)',
            color: 'var(--text)',
            fontSize: '12px',
          }}
          onKeyDown={e => { if (e.key === 'Enter') loadUsers(query) }}
        />
        <button
          type="button"
          onClick={() => loadUsers(query)}
          disabled={loading}
          style={{
            padding: '8px 12px',
            borderRadius: '8px',
            border: 'none',
            background: 'var(--primary)',
            color: 'var(--on-primary)',
            fontSize: '12px',
            fontWeight: 600,
            opacity: loading ? 0.6 : 1,
          }}
        >
          Apply
        </button>
      </div>

      <div style={{ marginTop: '14px', overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1100px' }}>
          <thead>
            <tr style={{ background: 'var(--table-header-bg)' }}>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Email</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>First Name</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Last Name</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Events</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Last Seen</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Types</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Admin</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={8} style={{ padding: '14px', textAlign: 'center', color: 'var(--text-secondary)', border: '1px solid var(--border)', fontSize: '12px' }}>
                  {loading ? 'Loading users...' : 'No user activity found.'}
                </td>
              </tr>
            )}
            {items.map(row => {
              const normalizedEmail = (row.email || '').trim().toLowerCase()
              const isAdmin = adminEmails.includes(normalizedEmail)
              const isUpdating = updatingEmail === normalizedEmail
              return (
                <tr key={row.email}>
                  <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>{row.email}</td>
                  <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>{row.first_name || '-'}</td>
                  <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>{row.last_name || '-'}</td>
                  <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>{row.event_count || 0}</td>
                  <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px', whiteSpace: 'nowrap' }}>{formatDate(row.last_seen)}</td>
                  <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>{(row.actor_types || []).join(', ') || '-'}</td>
                  <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: '999px',
                      border: '1px solid var(--border)',
                      color: isAdmin ? 'var(--success)' : 'var(--text-secondary)',
                      background: isAdmin ? 'var(--status-success-bg)' : 'var(--surface)',
                    }}>
                      {isAdmin ? 'Yes' : 'No'}
                    </span>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>
                    {isAdmin ? (
                      <button
                        type="button"
                        onClick={() => removeAdmin(normalizedEmail)}
                        disabled={isUpdating}
                        style={{
                          padding: '4px 10px',
                          borderRadius: '6px',
                          border: '1px solid var(--border)',
                          background: 'var(--surface)',
                          color: 'var(--text-secondary)',
                          fontSize: '11px',
                          opacity: isUpdating ? 0.6 : 1,
                        }}
                      >
                        {isUpdating ? 'Updating...' : 'Remove Admin'}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => makeAdmin(normalizedEmail)}
                        disabled={isUpdating}
                        style={{
                          padding: '4px 10px',
                          borderRadius: '6px',
                          border: 'none',
                          background: 'var(--primary)',
                          color: 'var(--on-primary)',
                          fontSize: '11px',
                          fontWeight: 600,
                          opacity: isUpdating ? 0.6 : 1,
                        }}
                      >
                        {isUpdating ? 'Updating...' : 'Make Admin'}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
