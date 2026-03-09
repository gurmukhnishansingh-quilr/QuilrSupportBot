import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { showToast } from '../utils/toast'

export default function FileManager({ authHeaders }) {
  const [documents, setDocuments] = useState([])
  const [uploading, setUploading] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const [message, setMessage] = useState(null)
  const fileInputRef = useRef(null)
  const [editingAccess, setEditingAccess] = useState(null) // { id, text }
  const [savingAccess, setSavingAccess] = useState(false)
  const [knownUsers, setKnownUsers] = useState([])

  const headers = authHeaders || {}

  useEffect(() => {
    loadDocuments()
    loadKnownUsers()
  }, [])

  useEffect(() => {
    if (!message?.text) return
    showToast(message)
    setMessage(null)
  }, [message])

  const loadDocuments = async () => {
    try {
      const res = await axios.get('/api/admin/documents', { headers })
      setDocuments(res.data)
    } catch (err) {
      setMessage({ type: 'error', text: 'Failed to load documents' })
    }
  }

  const loadKnownUsers = async () => {
    try {
      const res = await axios.get('/api/admin/users/activity', { headers, params: { limit: 500 } })
      const users = (res.data?.items || []).map(item => (item.email || '').trim().toLowerCase()).filter(Boolean)
      setKnownUsers([...new Set(users)])
    } catch {
      // ignore user suggestions fetch errors
    }
  }

  const uploadFiles = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    setUploading(true)
    setMessage(null)

    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }

    try {
      const res = await axios.post('/api/admin/documents/upload', formData, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      })
      const results = res.data
      const errors = results.filter(r => r.status === 'error')
      if (errors.length > 0) {
        setMessage({
          type: 'error',
          text: `${results.length - errors.length} uploaded, ${errors.length} failed`
        })
      } else {
        setMessage({
          type: 'success',
          text: `${results.length} document(s) uploaded and indexed`
        })
      }
      loadDocuments()
    } catch (err) {
      setMessage({ type: 'error', text: 'Upload failed' })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const deleteDocument = async (docId, filename) => {
    if (!confirm(`Delete "${filename}" and its embeddings?`)) return

    try {
      await axios.delete(`/api/admin/documents/${docId}`, { headers })
      setMessage({ type: 'success', text: `Deleted ${filename}` })
      loadDocuments()
    } catch (err) {
      setMessage({ type: 'error', text: 'Delete failed' })
    }
  }

  const [editingLink, setEditingLink] = useState(null) // { id, link }
  const [savingLink, setSavingLink] = useState(false)

  const saveLink = async (docId) => {
    if (!editingLink || editingLink.id !== docId) return
    setSavingLink(true)
    try {
      await axios.put(`/api/admin/documents/${docId}/link`,
        { link: editingLink.link },
        { headers }
      )
      setEditingLink(null)
      loadDocuments()
    } catch {
      setMessage({ type: 'error', text: 'Failed to save link' })
    } finally {
      setSavingLink(false)
    }
  }

  const parseEmailList = (value) => {
    return [...new Set(
      (value || '')
        .split(/[\n,;]+/)
        .map(v => v.trim().toLowerCase())
        .filter(Boolean)
    )]
  }

  const accessSuggestions = (text) => {
    const existing = parseEmailList(text)
    const token = ((text || '').split(/[\n,;]+/).pop() || '').trim().toLowerCase()
    return knownUsers
      .filter(email => !existing.includes(email))
      .filter(email => !token || email.includes(token))
      .slice(0, 8)
  }

  const addAccessEmail = (email) => {
    if (!editingAccess) return
    const existing = parseEmailList(editingAccess.text)
    if (existing.includes(email)) return
    const next = [...existing, email].join(', ')
    setEditingAccess({ ...editingAccess, text: next })
  }

  const saveAccess = async (docId) => {
    if (!editingAccess || editingAccess.id !== docId) return
    setSavingAccess(true)
    try {
      const emails = parseEmailList(editingAccess.text)
      await axios.put(`/api/admin/documents/${docId}/access`, { emails }, { headers })
      setEditingAccess(null)
      setMessage({
        type: 'success',
        text: emails.length > 0 ? 'Document access restricted to selected users' : 'Document access set to public',
      })
      loadDocuments()
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to save document access'
      setMessage({ type: 'error', text: detail })
    } finally {
      setSavingAccess(false)
    }
  }

  const reindexAll = async () => {
    if (!confirm('Re-process all documents? This may take a while.')) return

    setReindexing(true)
    setMessage(null)
    try {
      const res = await axios.post('/api/admin/documents/reindex', {}, { headers })
      setMessage({
        type: 'success',
        text: `Reindexed ${res.data.documents.length} document(s)`
      })
      loadDocuments()
    } catch (err) {
      setMessage({ type: 'error', text: 'Reindex failed' })
    } finally {
      setReindexing(false)
    }
  }

  return (
    <div style={{
      background: 'var(--surface)',
      borderRadius: '12px',
      border: '1px solid var(--border)',
      padding: '24px',
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '20px',
      }}>
        <h2 style={{ fontSize: '16px', fontWeight: 600 }}>Document Manager</h2>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: 'var(--primary)',
              color: 'var(--on-primary)',
              fontSize: '13px',
              fontWeight: 500,
              opacity: uploading ? 0.6 : 1,
            }}
          >
            {uploading ? 'Uploading...' : 'Upload PDFs'}
          </button>
          <button
            onClick={reindexAll}
            disabled={reindexing}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--text)',
              fontSize: '13px',
              fontWeight: 500,
              opacity: reindexing ? 0.6 : 1,
            }}
          >
            {reindexing ? 'Reindexing...' : 'Reindex All'}
          </button>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf"
          onChange={uploadFiles}
          style={{ display: 'none' }}
        />
      </div>

      {documents.length === 0 ? (
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', textAlign: 'center', padding: '32px 0' }}>
          No documents indexed yet
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {documents.map(doc => (
            <div key={doc.id} style={{
              padding: '12px',
              borderRadius: '8px',
              background: 'var(--bg)',
              border: '1px solid var(--border)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: '14px',
                    fontWeight: 500,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {doc.filename}
                  </div>
                  <div style={{
                    fontSize: '12px',
                    color: 'var(--text-secondary)',
                    marginTop: '2px',
                  }}>
                    {doc.chunk_count} chunks &middot; {doc.status} &middot; {new Date(doc.upload_date).toLocaleDateString()}
                  </div>
                </div>
                <button
                  onClick={() => deleteDocument(doc.id, doc.filename)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: '6px',
                    border: '1px solid var(--danger-soft-border)',
                    background: 'var(--danger-soft-bg)',
                    color: 'var(--error)',
                    fontSize: '12px',
                    fontWeight: 500,
                    marginLeft: '12px',
                    flexShrink: 0,
                  }}
                >
                  Delete
                </button>
              </div>
              {/* Document link */}
              <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                {editingLink && editingLink.id === doc.id ? (
                  <>
                    <input
                      type="url"
                      value={editingLink.link}
                      onChange={e => setEditingLink({ ...editingLink, link: e.target.value })}
                      placeholder="https://docs.example.com/..."
                      style={{
                        flex: 1,
                        padding: '5px 8px',
                        borderRadius: '6px',
                        border: '1px solid var(--border)',
                        fontSize: '12px',
                        outline: 'none',
                        background: 'var(--surface)',
                      }}
                      onKeyDown={e => { if (e.key === 'Enter') saveLink(doc.id) }}
                      autoFocus
                    />
                    <button
                      onClick={() => saveLink(doc.id)}
                      disabled={savingLink}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        border: 'none',
                        background: 'var(--primary)',
                        color: 'var(--on-primary)',
                        fontSize: '11px',
                        fontWeight: 500,
                      }}
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingLink(null)}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        border: '1px solid var(--border)',
                        background: 'var(--surface)',
                        color: 'var(--text-secondary)',
                        fontSize: '11px',
                      }}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    {doc.link ? (
                      <a
                        href={doc.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: '12px', color: 'var(--primary)', wordBreak: 'break-all' }}
                      >
                        {doc.link}
                      </a>
                    ) : (
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                        No link attached
                      </span>
                    )}
                    <button
                      onClick={() => setEditingLink({ id: doc.id, link: doc.link || '' })}
                      style={{
                        padding: '2px 8px',
                        borderRadius: '4px',
                        border: '1px solid var(--border)',
                        background: 'var(--surface)',
                        color: 'var(--text-secondary)',
                        fontSize: '11px',
                        flexShrink: 0,
                      }}
                    >
                      {doc.link ? 'Edit' : 'Add link'}
                    </button>
                  </>
                )}
              </div>

              <div style={{ marginTop: '8px' }}>
                {editingAccess && editingAccess.id === doc.id ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <input
                      type="text"
                      value={editingAccess.text}
                      onChange={e => setEditingAccess({ ...editingAccess, text: e.target.value })}
                      placeholder="user1@company.com, user2@company.com"
                      list="known-users-documents"
                      style={{
                        flex: 1,
                        padding: '5px 8px',
                        borderRadius: '6px',
                        border: '1px solid var(--border)',
                        fontSize: '12px',
                        outline: 'none',
                        background: 'var(--surface)',
                      }}
                      onKeyDown={e => { if (e.key === 'Enter') saveAccess(doc.id) }}
                      autoFocus
                    />
                    <datalist id="known-users-documents">
                      {knownUsers.map(email => (
                        <option key={email} value={email} />
                      ))}
                    </datalist>
                    <button
                      onClick={() => saveAccess(doc.id)}
                      disabled={savingAccess}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        border: 'none',
                        background: 'var(--primary)',
                        color: 'var(--on-primary)',
                        fontSize: '11px',
                        fontWeight: 500,
                        opacity: savingAccess ? 0.6 : 1,
                      }}
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingAccess(null)}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        border: '1px solid var(--border)',
                        background: 'var(--surface)',
                        color: 'var(--text-secondary)',
                        fontSize: '11px',
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {doc.is_restricted ? (
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        Restricted: {(doc.access_emails || []).join(', ')}
                      </span>
                    ) : (
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        Public: available to all users
                      </span>
                    )}
                    <button
                      onClick={() => setEditingAccess({
                        id: doc.id,
                        text: (doc.access_emails || []).join(', '),
                      })}
                      style={{
                        padding: '2px 8px',
                        borderRadius: '4px',
                        border: '1px solid var(--border)',
                        background: 'var(--surface)',
                        color: 'var(--text-secondary)',
                        fontSize: '11px',
                        flexShrink: 0,
                      }}
                    >
                      Manage access
                    </button>
                  </div>
                )}
                {editingAccess && editingAccess.id === doc.id && accessSuggestions(editingAccess.text).length > 0 && (
                  <div style={{ marginTop: '6px', display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {accessSuggestions(editingAccess.text).map(email => (
                      <button
                        key={email}
                        type="button"
                        onClick={() => addAccessEmail(email)}
                        style={{
                          padding: '2px 8px',
                          borderRadius: '999px',
                          border: '1px solid var(--border)',
                          background: 'var(--surface)',
                          color: 'var(--text-secondary)',
                          fontSize: '11px',
                        }}
                      >
                        {email}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
