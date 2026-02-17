import { useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import ChatMessage from '../components/ChatMessage'

export default function Chat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const sendMessage = async (e) => {
    e.preventDefault()
    const question = input.trim()
    if (!question || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: question }])
    setLoading(true)

    // Add placeholder for assistant
    const assistantIndex = messages.length + 1
    setMessages(prev => [...prev, { role: 'assistant', content: '', sources: [] }])

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let sources = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'content') {
              setMessages(prev => {
                const updated = [...prev]
                const last = updated[updated.length - 1]
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + data.content,
                }
                return updated
              })
            } else if (data.type === 'sources') {
              sources = data.sources
              setMessages(prev => {
                const updated = [...prev]
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  sources,
                }
                return updated
              })
            } else if (data.type === 'error') {
              setMessages(prev => {
                const updated = [...prev]
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  content: data.content,
                }
                return updated
              })
            }
          } catch {
            // skip malformed lines
          }
        }
      }
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          content: `Connection error: ${err.message}`,
        }
        return updated
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      background: 'var(--bg)',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 20px',
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <img src="/logo.png" alt="Quilr AI" style={{ height: '36px' }} />
          <div>
            <h1 style={{ fontSize: '18px', fontWeight: 600 }}>Quilly Support</h1>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Quilr AI Installation & Troubleshooting
            </p>
          </div>
        </div>
        <Link to="/admin" style={{
          fontSize: '13px',
          color: 'var(--text-secondary)',
          textDecoration: 'none',
          padding: '6px 12px',
          borderRadius: '6px',
          border: '1px solid var(--border)',
        }}>
          Admin
        </Link>
      </div>

      {/* Messages */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '20px 0',
      }}>
        {messages.length === 0 && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            color: 'var(--text-secondary)',
            textAlign: 'center',
            padding: '40px',
          }}>
            <img src="/logo.png" alt="Quilr AI" style={{
              height: '64px',
              marginBottom: '16px',
              opacity: 0.5,
            }} />
            <h2 style={{ fontSize: '20px', fontWeight: 500, marginBottom: '8px', color: 'var(--text)' }}>
              Welcome to Quilly Support
            </h2>
            <p style={{ maxWidth: '400px', lineHeight: '1.6' }}>
              Ask me anything about Quilr AI installation, tenant setup, or troubleshooting.
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}
        {loading && messages[messages.length - 1]?.content === '' && (
          <div style={{
            padding: '0 32px',
            color: 'var(--text-secondary)',
            fontSize: '14px',
          }}>
            Thinking...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={sendMessage} style={{
        display: 'flex',
        gap: '8px',
        padding: '16px 20px',
        background: 'var(--surface)',
        borderTop: '1px solid var(--border)',
        flexShrink: 0,
      }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about Quilr AI..."
          disabled={loading}
          style={{
            flex: 1,
            padding: '12px 16px',
            borderRadius: '12px',
            border: '1px solid var(--border)',
            fontSize: '14px',
            outline: 'none',
            background: 'var(--bg)',
          }}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          style={{
            padding: '12px 24px',
            borderRadius: '12px',
            border: 'none',
            background: 'var(--primary)',
            color: '#fff',
            fontSize: '14px',
            fontWeight: 500,
            opacity: loading || !input.trim() ? 0.5 : 1,
          }}
        >
          Send
        </button>
      </form>
    </div>
  )
}
