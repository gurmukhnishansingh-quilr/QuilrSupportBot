import { useState, useEffect } from 'react'
import axios from 'axios'

export default function LLMConfig({ authHeaders }) {
  const [config, setConfig] = useState({
    provider_type: 'openai',
    provider_url: '',
    api_key: '',
    model_name: '',
    api_version: '',
    include_video_transcripts_in_rag: false,
    temperature: 0.7,
    max_tokens: 1024,
  })
  const [masked, setMasked] = useState('')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [message, setMessage] = useState(null)

  const headers = authHeaders || {}

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    try {
      const res = await axios.get('/api/admin/config', { headers })
      setConfig({
        provider_type: res.data.provider_type || 'openai',
        provider_url: res.data.provider_url || '',
        api_key: '',
        model_name: res.data.model_name || '',
        api_version: res.data.api_version || '',
        include_video_transcripts_in_rag: !!res.data.include_video_transcripts_in_rag,
        temperature: res.data.temperature ?? 0.7,
        max_tokens: res.data.max_tokens ?? 1024,
      })
      setMasked(res.data.api_key_masked || '')
    } catch (err) {
      setMessage({ type: 'error', text: 'Failed to load config' })
    }
  }

  const saveConfig = async (e) => {
    e.preventDefault()
    setSaving(true)
    setMessage(null)
    try {
      const payload = { ...config }
      // If api_key is empty, user didn't change it — send the original
      // We need to send something, so we send a placeholder that backend can detect
      if (!payload.api_key && masked) {
        // Keep existing key by not changing it — but we need a workaround
        // Actually we need to pass something. Let user know.
        setMessage({ type: 'error', text: 'Please re-enter the API key to save' })
        setSaving(false)
        return
      }
      await axios.put('/api/admin/config', payload, { headers })
      setMessage({ type: 'success', text: 'Configuration saved' })
      loadConfig()
    } catch (err) {
      setMessage({ type: 'error', text: 'Failed to save config' })
    } finally {
      setSaving(false)
    }
  }

  const testConnection = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await axios.post('/api/admin/test-connection', {}, { headers })
      setTestResult(res.data)
    } catch (err) {
      setTestResult({ success: false, error: 'Request failed' })
    } finally {
      setTesting(false)
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
      <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>
        LLM Configuration
      </h2>

      <form onSubmit={saveConfig}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={labelStyle}>Provider Type</label>
            <div style={{ display: 'flex', gap: '8px' }}>
              {[
                { value: 'openai', label: 'OpenAI-compatible' },
                { value: 'azure', label: 'Azure OpenAI' },
              ].map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setConfig({ ...config, provider_type: opt.value })}
                  style={{
                    flex: 1,
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: `1px solid ${config.provider_type === opt.value ? 'var(--primary)' : 'var(--border)'}`,
                    background: config.provider_type === opt.value ? 'var(--primary)' : 'var(--surface)',
                    color: config.provider_type === opt.value ? 'var(--on-primary)' : 'var(--text)',
                    fontSize: '13px',
                    fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label style={labelStyle}>
              {config.provider_type === 'azure' ? 'Azure Endpoint' : 'Provider URL'}
            </label>
            <input
              style={inputStyle}
              type="url"
              value={config.provider_url}
              onChange={e => setConfig({ ...config, provider_url: e.target.value })}
              placeholder={config.provider_type === 'azure'
                ? 'https://your-resource.openai.azure.com'
                : 'https://api.openai.com/v1'}
            />
          </div>

          <div>
            <label style={labelStyle}>
              API Key {masked && <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>
                (current: {masked})
              </span>}
            </label>
            <input
              style={inputStyle}
              type="password"
              value={config.api_key}
              onChange={e => setConfig({ ...config, api_key: e.target.value })}
              placeholder={masked ? 'Enter new key to update' : 'Enter API key'}
            />
          </div>

          <div>
            <label style={labelStyle}>
              {config.provider_type === 'azure' ? 'Deployment Name' : 'Model Name'}
            </label>
            <input
              style={inputStyle}
              type="text"
              value={config.model_name}
              onChange={e => setConfig({ ...config, model_name: e.target.value })}
              placeholder={config.provider_type === 'azure' ? 'my-gpt-4o-deployment' : 'gpt-4o-mini'}
            />
          </div>

          {config.provider_type === 'azure' && (
            <div>
              <label style={labelStyle}>API Version</label>
              <input
                style={inputStyle}
                type="text"
                value={config.api_version}
                onChange={e => setConfig({ ...config, api_version: e.target.value })}
                placeholder="2024-12-01-preview"
              />
            </div>
          )}

          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 12px',
            borderRadius: '8px',
            border: '1px solid var(--border)',
            background: 'var(--bg)',
          }}>
            <input
              id="include-video-transcripts-in-rag"
              type="checkbox"
              checked={!!config.include_video_transcripts_in_rag}
              onChange={e => setConfig({
                ...config,
                include_video_transcripts_in_rag: e.target.checked,
              })}
            />
            <label
              htmlFor="include-video-transcripts-in-rag"
              style={{ fontSize: '13px', color: 'var(--text)' }}
            >
              Include video transcripts in RAG search
            </label>
          </div>

          <div style={{ display: 'flex', gap: '16px' }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Temperature: {config.temperature}</label>
              <input
                type="range"
                min="0" max="2" step="0.1"
                value={config.temperature}
                onChange={e => setConfig({ ...config, temperature: parseFloat(e.target.value) })}
                style={{ width: '100%' }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Max Tokens</label>
              <input
                style={inputStyle}
                type="number"
                min="1" max="128000"
                value={config.max_tokens}
                onChange={e => setConfig({ ...config, max_tokens: parseInt(e.target.value) || 1024 })}
              />
            </div>
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

        <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
          <button
            type="submit"
            disabled={saving}
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: 'none',
              background: 'var(--primary)',
              color: 'var(--on-primary)',
              fontSize: '14px',
              fontWeight: 500,
              opacity: saving ? 0.6 : 1,
            }}
          >
            {saving ? 'Saving...' : 'Save Config'}
          </button>
          <button
            type="button"
            onClick={testConnection}
            disabled={testing}
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--text)',
              fontSize: '14px',
              fontWeight: 500,
              opacity: testing ? 0.6 : 1,
            }}
          >
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
        </div>
      </form>

      {testResult && (
        <div style={{
          marginTop: '12px',
          padding: '12px',
          borderRadius: '8px',
          fontSize: '13px',
          background: testResult.success ? 'var(--status-success-bg)' : 'var(--status-error-bg)',
          border: `1px solid ${testResult.success ? 'var(--status-success-border)' : 'var(--status-error-border)'}`,
        }}>
          {testResult.success ? (
            <div>
              <strong style={{ color: 'var(--success)' }}>Connection successful</strong>
              <p style={{ marginTop: '4px', color: 'var(--text-secondary)' }}>
                Model: {testResult.model} — Response: {testResult.response}
              </p>
            </div>
          ) : (
            <div>
              <strong style={{ color: 'var(--error)' }}>Connection failed</strong>
              <p style={{ marginTop: '4px', color: 'var(--text-secondary)' }}>
                {testResult.error}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
