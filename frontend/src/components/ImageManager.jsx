import { useState, useEffect, useRef } from 'react'
import axios from 'axios'

export default function ImageManager({ password }) {
  const [images, setImages] = useState([])
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState(null)
  const [previewImage, setPreviewImage] = useState(null)
  const fileInputRef = useRef(null)

  const headers = { 'X-Admin-Password': password }

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
        <h2 style={{ fontSize: '16px', fontWeight: 600 }}>Image Manager</h2>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          style={{
            padding: '8px 16px',
            borderRadius: '8px',
            border: 'none',
            background: 'var(--primary)',
            color: '#fff',
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

      {message && (
        <div style={{
          marginBottom: '12px',
          padding: '8px 12px',
          borderRadius: '8px',
          fontSize: '13px',
          background: message.type === 'error' ? '#FEF2F2' : '#F0FDF4',
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
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
          gap: '12px',
        }}>
          {images.map(img => (
            <div key={img.id} style={{
              borderRadius: '8px',
              border: '1px solid var(--border)',
              background: 'var(--bg)',
              overflow: 'hidden',
            }}>
              <div
                onClick={() => setPreviewImage(img)}
                style={{
                  width: '100%',
                  height: '120px',
                  overflow: 'hidden',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: '#f5f5f5',
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
              <div style={{ padding: '8px' }}>
                <div style={{
                  fontSize: '12px',
                  fontWeight: 500,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  marginBottom: '4px',
                }}>
                  {img.original_name}
                </div>
                <div style={{
                  fontSize: '11px',
                  color: 'var(--text-secondary)',
                  marginBottom: '6px',
                }}>
                  {new Date(img.upload_date).toLocaleDateString()}
                </div>
                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    onClick={() => copyUrl(img.filename)}
                    style={{
                      flex: 1,
                      padding: '4px 6px',
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
                      padding: '4px 6px',
                      borderRadius: '4px',
                      border: '1px solid #FECACA',
                      background: '#FEF2F2',
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
            background: 'rgba(0,0,0,0.7)',
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
                maxHeight: 'calc(90vh - 80px)',
                objectFit: 'contain',
                borderRadius: '8px',
              }}
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontSize: '13px', fontWeight: 500 }}>
                {previewImage.original_name}
              </span>
              <button
                onClick={() => setPreviewImage(null)}
                style={{
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
