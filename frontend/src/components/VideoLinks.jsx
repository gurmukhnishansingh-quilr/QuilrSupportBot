import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

export default function VideoLinks({ authHeaders }) {
  const [links, setLinks] = useState([])
  const [form, setForm] = useState({ title: '', url: '', description: '', transcript: '' })
  const [adding, setAdding] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [updatingTranscriptId, setUpdatingTranscriptId] = useState(null)
  const [uploadVideoFile, setUploadVideoFile] = useState(null)
  const [uploadTranscriptFile, setUploadTranscriptFile] = useState(null)
  const [transcriptDrafts, setTranscriptDrafts] = useState({})
  const [transcriptFiles, setTranscriptFiles] = useState({})
  const [message, setMessage] = useState(null)
  const videoInputRef = useRef(null)
  const transcriptInputRef = useRef(null)
  const transcriptUpdateInputRefs = useRef({})

  const headers = authHeaders || {}

  useEffect(() => {
    loadLinks()
  }, [])

  const loadLinks = async () => {
    try {
      const res = await axios.get('/api/admin/video-links', { headers })
      setLinks(res.data)
      setTranscriptDrafts(prev => {
        const next = {}
        for (const link of res.data) {
          const hasDraft = Object.prototype.hasOwnProperty.call(prev, link.id)
          next[link.id] = hasDraft ? prev[link.id] : (link.transcript || '')
        }
        return next
      })
      setTranscriptFiles(prev => {
        const next = {}
        for (const link of res.data) {
          if (prev[link.id]) next[link.id] = prev[link.id]
        }
        return next
      })
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
      setForm({ title: '', url: '', description: '', transcript: '' })
      setMessage({ type: 'success', text: 'Video link added' })
      loadLinks()
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to add video link'
      setMessage({ type: 'error', text: detail })
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

  const uploadVideo = async () => {
    if (!uploadVideoFile) return
    setUploading(true)
    setMessage(null)
    const formData = new FormData()
    formData.append('file', uploadVideoFile)
    if (uploadTranscriptFile) {
      formData.append('transcript_file', uploadTranscriptFile)
    }
    try {
      await axios.post('/api/admin/video-links/upload', formData, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      })
      const transcriptNote = uploadTranscriptFile ? ' with transcript' : ''
      setMessage({ type: 'success', text: `Uploaded "${uploadVideoFile.name}"${transcriptNote}` })
      loadLinks()
    } catch (err) {
      const detail = err.response?.data?.detail || 'Upload failed'
      setMessage({ type: 'error', text: detail })
    } finally {
      setUploading(false)
      setUploadVideoFile(null)
      setUploadTranscriptFile(null)
      if (videoInputRef.current) videoInputRef.current.value = ''
      if (transcriptInputRef.current) transcriptInputRef.current.value = ''
    }
  }

  const updateTranscript = async (link) => {
    const transcriptFile = transcriptFiles[link.id]
    const transcriptText = transcriptDrafts[link.id] || ''
    setUpdatingTranscriptId(link.id)
    setMessage(null)

    const formData = new FormData()
    if (transcriptFile) {
      formData.append('transcript_file', transcriptFile)
    } else {
      formData.append('transcript_text', transcriptText)
    }

    try {
      const res = await axios.put(`/api/admin/video-links/${link.id}/transcript`, formData, {
        headers: { ...headers, 'Content-Type': 'multipart/form-data' },
      })
      const savedTranscript = res.data.transcript || ''
      setTranscriptDrafts(prev => ({ ...prev, [link.id]: savedTranscript }))
      setTranscriptFiles(prev => {
        const next = { ...prev }
        delete next[link.id]
        return next
      })
      const input = transcriptUpdateInputRefs.current[link.id]
      if (input) input.value = ''
      setMessage({
        type: 'success',
        text: savedTranscript ? `Updated transcript for "${link.title}"` : `Removed transcript from "${link.title}"`,
      })
      loadLinks()
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to update transcript'
      setMessage({ type: 'error', text: detail })
    } finally {
      setUpdatingTranscriptId(null)
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
      <div style={{ marginBottom: '4px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 600 }}>
          Video Links
        </h2>
      </div>
      <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px' }}>
        Upload videos or add external links (YouTube, Vimeo). Quilly will share these when users ask for demos.
      </p>

      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        padding: '12px',
        borderRadius: '8px',
        background: 'var(--bg)',
        border: '1px solid var(--border)',
        marginBottom: '20px',
      }}>
        <div style={{ fontSize: '13px', fontWeight: 600 }}>Upload Local Video</div>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            onClick={() => videoInputRef.current?.click()}
            disabled={uploading}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--text)',
              fontSize: '12px',
            }}
          >
            {uploadVideoFile ? 'Change Video' : 'Select Video'}
          </button>
          <button
            onClick={() => transcriptInputRef.current?.click()}
            disabled={uploading}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--text)',
              fontSize: '12px',
            }}
          >
            {uploadTranscriptFile ? 'Change Transcript' : 'Add Transcript (Optional)'}
          </button>
          <button
            onClick={uploadVideo}
            disabled={uploading || !uploadVideoFile}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: 'none',
              background: 'var(--primary)',
              color: 'var(--on-primary)',
              fontSize: '12px',
              opacity: uploading || !uploadVideoFile ? 0.6 : 1,
            }}
          >
            {uploading ? 'Uploading...' : 'Upload Video'}
          </button>
        </div>
        <input
          ref={videoInputRef}
          type="file"
          accept=".mp4,.webm,.ogg,.mov"
          onChange={e => setUploadVideoFile(e.target.files?.[0] || null)}
          style={{ display: 'none' }}
        />
        <input
          ref={transcriptInputRef}
          type="file"
          accept=".txt,.srt,.vtt,.md"
          onChange={e => setUploadTranscriptFile(e.target.files?.[0] || null)}
          style={{ display: 'none' }}
        />
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          {uploadVideoFile ? `Video: ${uploadVideoFile.name}` : 'No video selected'}
          {' · '}
          {uploadTranscriptFile ? `Transcript: ${uploadTranscriptFile.name}` : 'No transcript selected'}
        </div>
      </div>

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
                {link.transcript && (
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                    Transcript attached
                  </div>
                )}
                <div style={{ marginTop: '8px' }}>
                  <textarea
                    style={{ ...inputStyle, minHeight: '72px', resize: 'vertical', fontSize: '12px' }}
                    value={transcriptDrafts[link.id] || ''}
                    onChange={e => setTranscriptDrafts(prev => ({ ...prev, [link.id]: e.target.value }))}
                    placeholder="Paste transcript text for this video (optional)"
                  />
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '6px' }}>
                    <button
                      onClick={() => transcriptUpdateInputRefs.current[link.id]?.click()}
                      disabled={updatingTranscriptId === link.id}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        border: '1px solid var(--border)',
                        background: 'var(--surface)',
                        color: 'var(--text)',
                        fontSize: '12px',
                      }}
                    >
                      {transcriptFiles[link.id] ? 'Change Transcript File' : 'Upload Transcript File'}
                    </button>
                    <button
                      onClick={() => updateTranscript(link)}
                      disabled={
                        updatingTranscriptId === link.id ||
                        (!transcriptFiles[link.id] &&
                          (transcriptDrafts[link.id] || '').trim() === (link.transcript || '').trim())
                      }
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        border: 'none',
                        background: 'var(--primary)',
                        color: 'var(--on-primary)',
                        fontSize: '12px',
                        opacity:
                          updatingTranscriptId === link.id ||
                          (!transcriptFiles[link.id] &&
                            (transcriptDrafts[link.id] || '').trim() === (link.transcript || '').trim())
                            ? 0.6 : 1,
                      }}
                    >
                      {updatingTranscriptId === link.id ? 'Saving...' : 'Save Transcript'}
                    </button>
                    <button
                      onClick={() => setTranscriptDrafts(prev => ({ ...prev, [link.id]: '' }))}
                      disabled={updatingTranscriptId === link.id}
                      style={{
                        padding: '4px 10px',
                        borderRadius: '6px',
                        border: '1px solid var(--border)',
                        background: 'var(--surface)',
                        color: 'var(--text-secondary)',
                        fontSize: '12px',
                      }}
                    >
                      Clear
                    </button>
                  </div>
                  <input
                    ref={el => {
                      transcriptUpdateInputRefs.current[link.id] = el
                    }}
                    type="file"
                    accept=".txt,.srt,.vtt,.md"
                    onChange={e => {
                      const file = e.target.files?.[0] || null
                      setTranscriptFiles(prev => ({ ...prev, [link.id]: file }))
                    }}
                    style={{ display: 'none' }}
                  />
                  {transcriptFiles[link.id] && (
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                      Selected file: {transcriptFiles[link.id].name}
                    </div>
                  )}
                </div>
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
          <div>
            <label style={labelStyle}>Transcript (optional)</label>
            <textarea
              style={{ ...inputStyle, minHeight: '96px', resize: 'vertical' }}
              value={form.transcript}
              onChange={e => setForm({ ...form, transcript: e.target.value })}
              placeholder="Paste transcript text so Quilly can understand the video context"
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
          disabled={adding || !form.title.trim() || !form.url.trim()}
          style={{
            marginTop: '12px',
            padding: '10px 20px',
            borderRadius: '8px',
            border: 'none',
            background: 'var(--primary)',
            color: 'var(--on-primary)',
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
