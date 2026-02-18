import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'

function getVideoEmbed(url) {
  try {
    const u = new URL(url)

    // YouTube: youtube.com/watch?v=ID or youtu.be/ID
    if (u.hostname.includes('youtube.com') || u.hostname.includes('youtu.be')) {
      let videoId = u.searchParams.get('v')
      if (!videoId && u.hostname.includes('youtu.be')) {
        videoId = u.pathname.slice(1)
      }
      if (videoId) {
        return `https://www.youtube.com/embed/${videoId}`
      }
    }

    // Vimeo: vimeo.com/ID
    if (u.hostname.includes('vimeo.com')) {
      const match = u.pathname.match(/\/(\d+)/)
      if (match) {
        return `https://player.vimeo.com/video/${match[1]}`
      }
    }
  } catch {
    // not a valid URL
  }
  return null
}

const LOCAL_VIDEO_EXTS = ['.mp4', '.webm', '.ogg', '.mov']

function isLocalVideo(url) {
  if (!url) return false
  if (url.startsWith('/api/videos/')) return true
  try {
    const pathname = new URL(url, window.location.origin).pathname
    return LOCAL_VIDEO_EXTS.some(ext => pathname.toLowerCase().endsWith(ext))
  } catch {
    return false
  }
}

function NativeVideoPlayer({ src, title }) {
  return (
    <div style={{ margin: '8px 0' }}>
      <video
        controls
        preload="metadata"
        style={{
          width: '100%',
          maxHeight: '360px',
          borderRadius: '8px',
          background: '#000',
        }}
      >
        <source src={src} />
        Your browser does not support the video tag.
      </video>
      {title && (
        <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          {title}
        </div>
      )}
    </div>
  )
}

function IframeVideoPlayer({ embedUrl, title, href }) {
  return (
    <div style={{ margin: '8px 0' }}>
      <div style={{
        position: 'relative',
        paddingBottom: '56.25%',
        height: 0,
        borderRadius: '8px',
        overflow: 'hidden',
        background: '#000',
      }}>
        <iframe
          src={embedUrl}
          title={title || 'Video'}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            border: 'none',
          }}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        style={{ fontSize: '11px', color: 'var(--primary)', marginTop: '4px', display: 'inline-block' }}
      >
        {title || href}
      </a>
    </div>
  )
}

function ChatImage({ src, alt }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <>
      <div
        style={{
          margin: '8px 0',
          borderRadius: '8px',
          overflow: 'hidden',
          border: '1px solid var(--border)',
          background: '#f8f8f8',
          cursor: 'pointer',
        }}
        onClick={() => setExpanded(true)}
      >
        <img
          src={src}
          alt={alt || ''}
          style={{
            display: 'block',
            maxWidth: '100%',
            maxHeight: '300px',
            objectFit: 'contain',
            margin: '0 auto',
          }}
        />
        {alt && (
          <div style={{
            padding: '6px 10px',
            fontSize: '11px',
            color: 'var(--text-secondary)',
            borderTop: '1px solid var(--border)',
            background: 'var(--surface)',
          }}>
            {alt}
          </div>
        )}
      </div>

      {expanded && (
        <div
          onClick={() => setExpanded(false)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.75)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '24px',
            cursor: 'zoom-out',
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: 'var(--surface)',
              borderRadius: '12px',
              padding: '12px',
              maxWidth: '90vw',
              maxHeight: '90vh',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <img
              src={src}
              alt={alt || ''}
              style={{
                maxWidth: '100%',
                maxHeight: 'calc(90vh - 80px)',
                objectFit: 'contain',
                borderRadius: '8px',
              }}
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              {alt && (
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{alt}</span>
              )}
              <button
                onClick={() => setExpanded(false)}
                style={{
                  padding: '5px 14px',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  background: 'var(--surface)',
                  color: 'var(--text)',
                  fontSize: '12px',
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function CustomLink({ href, children }) {
  const title = typeof children === 'string' ? children
    : Array.isArray(children) ? children.map(c => (typeof c === 'string' ? c : '')).join('') : ''

  // Local/uploaded video files → HTML5 player
  if (isLocalVideo(href)) {
    return <NativeVideoPlayer src={href} title={title} />
  }

  // YouTube/Vimeo → iframe embed
  const embedUrl = getVideoEmbed(href || '')
  if (embedUrl) {
    return <IframeVideoPlayer embedUrl={embedUrl} title={title} href={href} />
  }

  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  )
}

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user'

  return (
    <div style={{
      display: 'flex',
      justifyContent: isUser ? 'flex-end' : 'flex-start',
      marginBottom: '16px',
      padding: '0 16px',
    }}>
      <div style={{
        maxWidth: '75%',
        padding: '12px 16px',
        borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
        background: isUser ? 'var(--user-bubble)' : 'var(--assistant-bubble)',
        color: isUser ? '#fff' : 'var(--text)',
        fontSize: '14px',
        lineHeight: '1.5',
        wordBreak: 'break-word',
      }}>
        {isUser ? (
          <p style={{ margin: 0 }}>{message.content}</p>
        ) : (
          <div className="markdown-content">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
              components={{ a: CustomLink, img: ChatImage }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
