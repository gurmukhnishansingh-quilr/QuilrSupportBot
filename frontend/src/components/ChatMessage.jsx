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

function CustomImage({ src, alt }) {
  return (
    <img
      src={src}
      alt={alt || ''}
      style={{
        maxWidth: '100%',
        maxHeight: '400px',
        borderRadius: '8px',
        marginTop: '4px',
        marginBottom: '4px',
        objectFit: 'contain',
        cursor: 'pointer',
      }}
      onClick={() => window.open(src, '_blank')}
    />
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
              components={{ a: CustomLink, img: CustomImage }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
