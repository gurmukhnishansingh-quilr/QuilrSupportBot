import { useEffect, useState } from 'react'
import { applyTheme, getStoredTheme } from '../utils/theme'
import { showToast } from '../utils/toast'

export default function AppearanceSettings() {
  const [theme, setTheme] = useState('light')

  useEffect(() => {
    setTheme(getStoredTheme())
  }, [])

  const updateTheme = (nextTheme) => {
    const applied = applyTheme(nextTheme)
    setTheme(applied)
    showToast({
      type: 'success',
      text: `Theme updated to ${applied === 'dark' ? 'Dark' : 'Light'} mode`,
    })
  }

  const buttonStyle = (isActive) => ({
    padding: '8px 14px',
    borderRadius: '8px',
    border: `1px solid ${isActive ? 'var(--primary)' : 'var(--border)'}`,
    background: isActive ? 'var(--primary-light)' : 'var(--surface)',
    color: isActive ? 'var(--primary)' : 'var(--text)',
    fontSize: '13px',
    fontWeight: 500,
  })

  return (
    <div style={{
      background: 'var(--surface)',
      borderRadius: '12px',
      border: '1px solid var(--border)',
      padding: '24px',
    }}>
      <h2 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '14px' }}>
        Appearance
      </h2>
      <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
        Choose how the admin portal looks.
      </p>
      <div style={{ display: 'flex', gap: '8px' }}>
        <button
          type="button"
          onClick={() => updateTheme('light')}
          style={buttonStyle(theme === 'light')}
        >
          Light
        </button>
        <button
          type="button"
          onClick={() => updateTheme('dark')}
          style={buttonStyle(theme === 'dark')}
        >
          Dark
        </button>
      </div>
    </div>
  )
}
