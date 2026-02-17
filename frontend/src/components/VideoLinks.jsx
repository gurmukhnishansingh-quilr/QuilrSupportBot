import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

export default function VideoLinks({ password }) {
  const [links, setLinks] = useState([])
  const [form, setForm] = useState({ title: '', url: '', description: '' })
  const [adding, setAdding] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState(null)
  const fileInputRef = useRef(null)

  const headers = { 'X-Admin-Password': password }

  useEffect(() => {
    loadLinks()
  }, [])

  const loadLinks = async () => {
    try {
      const res = await axios.get('/api/admin/video-links', { headers })
      setLinks(res.data)
    } catch {
      setMessage({ type: 'error', text: 'Failed to load video links' })
    }
  }

  const addLink = async (e) => {
    e.preventDefault()
    if (!form.title.trim() || !form.url.trim()) return
    setAdding(true)
    setMessage(null)
    try {
      await axios.post('/api/admin/video-links', form, { headers })
      setForm({ title: '', url: '', description: '' })
      setMessage({ type: 'success', text: 'Video link added' })
      loadLinks()
    } catch {
      setMessage({ type: 'error', text: 'Failed to add video link' })
    } finally {
      setAdding(false)
    }
  }

  const removeLink = async (id) => {
    try {
      await axios.delete(`/api/admin/video-links/${id}`, { headers })
      loadLinks()
    } catch {
      setMessage({ type: 'error', text: 'Failed to delete video link' })
    }
  }

  const uploadVideo = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setMessage(null)
    const formData = new FormData()
    formData.append('file', file)
    try {
      await axios.post('/api/admin/video-links/upload', formData, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      })
      setMessage({ type: 'success', text: `Uploaded "${file.name}"` })
      loadLinks()
    } catch (err) {
      const detail = err.response?.data?.detail || 'Upload failed'
      setMessage({ type: 'error', text: detail })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 600 }}>
          Video Links
        </h2>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          style={{
            padding: '6px 14px',
            borderRadius: '8px',
            border: 'none',
            background: 'var(--primary)',
            color: '#fff',
            fontSize: '13px',
            fontWeight: 500,
            opacity: uploading ? 0.6 : 1,
          }}
        >
          {uploading ? 'Uploading...' : 'Upload Video'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".mp4,.webm,.ogg,.mov"
          onChange={uploadVideo}
          style={{ display: 'none' }}
        />
      </div>
      <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px' }}>
        Upload videos or add external links (YouTube, Vimeo). Quilly will share these when users ask for demos.
      </p>

      {/* Existing links */}
      {links.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '20px' }}>
          {links.map(link => (
            <div key={link.id} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              padding: '10px 12px',
              borderRadius: '8px',
              background: 'var(--bg)',
              border: '1px solid var(--border)',
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '14px', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {link.title}
                  {link.url.startsWith('/api/videos/') && (
                    <span style={{
                      fontSize: '10px',
                      padding: '1px 6px',
                      borderRadius: '4px',
                      background: 'var(--primary-light)',
                      color: 'var(--primary)',
                      fontWeight: 600,
                    }}>
                      Uploaded
                    </span>
                  )}
                </div>
                <a
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    fontSize: '12px',
                    color: 'var(--primary)',
                    wordBreak: 'break-all',
                  }}
                >
                  {link.url}
                </a>
                {link.description && (
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                    {link.description}
                  </div>
                )}
              </div>
              <button
                onClick={() => removeLink(link.id)}
                style={{
                  padding: '4px 10px',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  background: 'var(--surface)',
                  color: 'var(--error)',
                  fontSize: '12px',
                  flexShrink: 0,
                }}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add form */}
      <form onSubmit={addLink}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div>
            <label style={labelStyle}>Title</label>
            <input
              style={inputStyle}
              type="text"
              value={form.title}
              onChange={e => setForm({ ...form, title: e.target.value })}
              placeholder="e.g. Quilr AI Installation Walkthrough"
            />
          </div>
          <div>
            <label style={labelStyle}>URL</label>
            <input
              style={inputStyle}
              type="url"
              value={form.url}
              onChange={e => setForm({ ...form, url: e.target.value })}
              placeholder="https://www.youtube.com/watch?v=..."
            />
          </div>
          <div>
            <label style={labelStyle}>Description (optional)</label>
            <input
              style={inputStyle}
              type="text"
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              placeholder="Brief description of the video content"
            />
          </div>
        </div>

        {message && (
          <div style={{
            marginTop: '12px',
            padding: '8px 12px',
            borderRadius: '8px',
            fontSize: '13px',
            background: message.type === 'error' ? '#FEF2F2' : '#F0FDF4',
            color: message.type === 'error' ? 'var(--error)' : 'var(--success)',
          }}>
            {message.text}
          </div>
        )}

        <button
          type="submit"
          disabled={adding || !form.title.trim() || !form.url.trim()}
          style={{
            marginTop: '12px',
            padding: '10px 20px',
            borderRadius: '8px',
            border: 'none',
            background: 'var(--primary)',
            color: '#fff',
            fontSize: '14px',
            fontWeight: 500,
            opacity: adding || !form.title.trim() || !form.url.trim() ? 0.6 : 1,
          }}
        >
          {adding ? 'Adding...' : 'Add Video Link'}
        </button>
      </form>
    </div>
  )
}
