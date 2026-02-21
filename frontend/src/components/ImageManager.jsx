import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

export default function ImageManager({ authHeaders }) {
  const [images, setImages] = useState([])
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState(null)
  const [previewImage, setPreviewImage] = useState(null)
  const [editingDesc, setEditingDesc] = useState(null) // { id, description }
  const [savingDesc, setSavingDesc] = useState(false)
  const fileInputRef = useRef(null)

  const headers = authHeaders || {}

  useEffect(() => {
    loadImages()
  }, [])

  const loadImages = async () => {
    try {
      const res = await axios.get('/api/admin/images', { headers })
      setImages(res.data)
    } catch (err) {
      setMessage({ type: 'error', text: 'Failed to load images' })
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
      const res = await axios.post('/api/admin/images/upload', formData, {
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
          text: `${results.length} image(s) uploaded`
        })
      }
      loadImages()
    } catch (err) {
      setMessage({ type: 'error', text: 'Upload failed' })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const deleteImage = async (imageId, name) => {
    if (!confirm(`Delete "${name}"?`)) return

    try {
      await axios.delete(`/api/admin/images/${imageId}`, { headers })
      setMessage({ type: 'success', text: `Deleted ${name}` })
      loadImages()
    } catch (err) {
      setMessage({ type: 'error', text: 'Delete failed' })
    }
  }

  const copyUrl = (filename) => {
    const url = `${window.location.origin}/api/images/${filename}`
    navigator.clipboard.writeText(url)
    setMessage({ type: 'success', text: 'URL copied to clipboard' })
  }

  const saveDescription = async (imageId) => {
    if (!editingDesc || editingDesc.id !== imageId) return
    setSavingDesc(true)
    try {
      await axios.put(`/api/admin/images/${imageId}/description`,
        { description: editingDesc.description },
        { headers }
      )
      setEditingDesc(null)
      loadImages()
    } catch {
      setMessage({ type: 'error', text: 'Failed to save description' })
    } finally {
      setSavingDesc(false)
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
        marginBottom: '4px',
      }}>
        <h2 style={{ fontSize: '16px', fontWeight: 600 }}>Image Manager</h2>
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
          {uploading ? 'Uploading...' : 'Upload Images'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*"
          onChange={uploadFiles}
          style={{ display: 'none' }}
        />
      </div>
      <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
        Add descriptions so the chatbot can share relevant images with users.
      </p>

      {message && (
        <div style={{
          marginBottom: '12px',
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

      {images.length === 0 ? (
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', textAlign: 'center', padding: '32px 0' }}>
          No images uploaded yet
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {images.map(img => (
            <div key={img.id} style={{
              display: 'flex',
              gap: '12px',
              padding: '12px',
              borderRadius: '8px',
              background: 'var(--bg)',
              border: '1px solid var(--border)',
            }}>
              {/* Thumbnail */}
              <div
                onClick={() => setPreviewImage(img)}
                style={{
                  width: '80px',
                  height: '80px',
                  flexShrink: 0,
                  overflow: 'hidden',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'var(--media-bg)',
                  borderRadius: '6px',
                }}
              >
                <img
                  src={`/api/images/${img.filename}`}
                  alt={img.original_name}
                  style={{
                    maxWidth: '100%',
                    maxHeight: '100%',
                    objectFit: 'contain',
                  }}
                />
              </div>

              {/* Details */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: '13px',
                  fontWeight: 500,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {img.original_name}
                </div>
                <div style={{
                  fontSize: '11px',
                  color: 'var(--text-secondary)',
                  marginTop: '2px',
                  marginBottom: '6px',
                }}>
                  {new Date(img.upload_date).toLocaleDateString()}
                </div>

                {/* Description */}
                {editingDesc && editingDesc.id === img.id ? (
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'flex-start' }}>
                    <textarea
                      value={editingDesc.description}
                      onChange={e => setEditingDesc({ ...editingDesc, description: e.target.value })}
                      placeholder="Describe this image for the chatbot (e.g. 'Screenshot of the MDM enrollment screen showing step 3')"
                      rows={2}
                      style={{
                        flex: 1,
                        padding: '6px 8px',
                        borderRadius: '6px',
                        border: '1px solid var(--border)',
                        fontSize: '12px',
                        outline: 'none',
                        background: 'var(--surface)',
                        resize: 'vertical',
                        fontFamily: 'inherit',
                      }}
                      autoFocus
                    />
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <button
                        onClick={() => saveDescription(img.id)}
                        disabled={savingDesc}
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
                        onClick={() => setEditingDesc(null)}
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
                  </div>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
                    {img.description ? (
                      <span style={{ fontSize: '12px', color: 'var(--text)', lineHeight: '1.4' }}>
                        {img.description}
                      </span>
                    ) : (
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                        No description
                      </span>
                    )}
                    <button
                      onClick={() => setEditingDesc({ id: img.id, description: img.description || '' })}
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
                      {img.description ? 'Edit' : 'Add'}
                    </button>
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: 'flex', gap: '4px', marginTop: '6px' }}>
                  <button
                    onClick={() => copyUrl(img.filename)}
                    style={{
                      padding: '4px 8px',
                      borderRadius: '4px',
                      border: '1px solid var(--border)',
                      background: 'var(--surface)',
                      color: 'var(--text-secondary)',
                      fontSize: '11px',
                    }}
                  >
                    Copy URL
                  </button>
                  <button
                    onClick={() => deleteImage(img.id, img.original_name)}
                    style={{
                      padding: '4px 8px',
                      borderRadius: '4px',
                      border: '1px solid var(--danger-soft-border)',
                      background: 'var(--danger-soft-bg)',
                      color: 'var(--error)',
                      fontSize: '11px',
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Image Preview Modal */}
      {previewImage && (
        <div
          onClick={() => setPreviewImage(null)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'var(--overlay)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '24px',
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: 'var(--surface)',
              borderRadius: '12px',
              padding: '16px',
              maxWidth: '90vw',
              maxHeight: '90vh',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <img
              src={`/api/images/${previewImage.filename}`}
              alt={previewImage.original_name}
              style={{
                maxWidth: '100%',
                maxHeight: 'calc(90vh - 100px)',
                objectFit: 'contain',
                borderRadius: '8px',
              }}
            />
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '13px', fontWeight: 500 }}>
                {previewImage.original_name}
              </div>
              {previewImage.description && (
                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  {previewImage.description}
                </div>
              )}
              <button
                onClick={() => setPreviewImage(null)}
                style={{
                  marginTop: '8px',
                  padding: '6px 16px',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  background: 'var(--surface)',
                  color: 'var(--text)',
                  fontSize: '12px',
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
