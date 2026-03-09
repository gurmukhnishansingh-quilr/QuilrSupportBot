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

function formatMetadata(row) {
  const payload = row.metadata_json ?? row.metadata
  if (!payload) return '-'
  if (typeof payload === 'string') return payload
  try {
    return JSON.stringify(payload)
  } catch {
    return String(payload)
  }
}

export default function AuditLogs({ authHeaders }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState({
    event_type: '',
    actor_email: '',
    status: '',
  })

  const headers = authHeaders || {}

  const loadLogs = async () => {
    setLoading(true)
    try {
      const params = { limit: 300 }
      if (filters.event_type.trim()) params.event_type = filters.event_type.trim()
      if (filters.actor_email.trim()) params.actor_email = filters.actor_email.trim().toLowerCase()
      if (filters.status) params.status = filters.status
      const res = await axios.get('/api/admin/audit-logs', { headers, params })
      setItems(res.data?.items || [])
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to load audit logs'
      showToast({ type: 'error', text: detail })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLogs()
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
          <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>Audit Logs</h2>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            System activity across authentication, admin actions, and content events.
          </p>
        </div>
        <button
          type="button"
          onClick={loadLogs}
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

      <div style={{ marginTop: '12px', display: 'grid', gridTemplateColumns: '1fr 1fr 180px auto', gap: '8px' }}>
        <input
          type="text"
          value={filters.event_type}
          onChange={e => setFilters(prev => ({ ...prev, event_type: e.target.value }))}
          placeholder="Event type (e.g. admin.video_delete)"
          style={{
            padding: '8px 10px',
            borderRadius: '8px',
            border: '1px solid var(--border)',
            background: 'var(--bg)',
            color: 'var(--text)',
            fontSize: '12px',
          }}
        />
        <input
          type="email"
          value={filters.actor_email}
          onChange={e => setFilters(prev => ({ ...prev, actor_email: e.target.value }))}
          placeholder="Actor email"
          style={{
            padding: '8px 10px',
            borderRadius: '8px',
            border: '1px solid var(--border)',
            background: 'var(--bg)',
            color: 'var(--text)',
            fontSize: '12px',
          }}
        />
        <select
          value={filters.status}
          onChange={e => setFilters(prev => ({ ...prev, status: e.target.value }))}
          style={{
            padding: '8px 10px',
            borderRadius: '8px',
            border: '1px solid var(--border)',
            background: 'var(--bg)',
            color: 'var(--text)',
            fontSize: '12px',
          }}
        >
          <option value="">All statuses</option>
          <option value="success">Success</option>
          <option value="error">Error</option>
        </select>
        <button
          type="button"
          onClick={loadLogs}
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
          Apply Filters
        </button>
      </div>

      <div style={{ marginTop: '14px', overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '1200px' }}>
          <thead>
            <tr style={{ background: 'var(--table-header-bg)' }}>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Time</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Event</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Status</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Actor Type</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Actor Email</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Target</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Message</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>IP</th>
              <th style={{ textAlign: 'left', padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>Metadata</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={9} style={{ padding: '14px', textAlign: 'center', color: 'var(--text-secondary)', border: '1px solid var(--border)', fontSize: '12px' }}>
                  {loading ? 'Loading logs...' : 'No audit logs found.'}
                </td>
              </tr>
            )}
            {items.map(row => (
              <tr key={row.id}>
                <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px', whiteSpace: 'nowrap' }}>{formatDate(row.created_at)}</td>
                <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px', whiteSpace: 'nowrap' }}>{row.event_type || '-'}</td>
                <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: '999px',
                    border: '1px solid var(--border)',
                    color: row.status === 'error' ? 'var(--error)' : 'var(--success)',
                    background: row.status === 'error' ? 'var(--status-error-bg)' : 'var(--status-success-bg)',
                  }}>
                    {row.status || '-'}
                  </span>
                </td>
                <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>{row.actor_type || '-'}</td>
                <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>{row.actor_email || '-'}</td>
                <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>
                  {row.target_type || '-'}{row.target_id ? `:${row.target_id}` : ''}
                </td>
                <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px', maxWidth: '240px', wordBreak: 'break-word' }}>{row.message || '-'}</td>
                <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px' }}>{row.ip_address || '-'}</td>
                <td style={{ padding: '8px', border: '1px solid var(--border)', fontSize: '12px', maxWidth: '420px', wordBreak: 'break-word' }}>{formatMetadata(row)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
