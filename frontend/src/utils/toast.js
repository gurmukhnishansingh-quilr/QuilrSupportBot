const listeners = new Set()

export function showToast({ type = 'info', text = '', duration = 3500 }) {
  const trimmed = String(text || '').trim()
  if (!trimmed) return
  const payload = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    type,
    text: trimmed,
    duration: Number(duration) > 0 ? Number(duration) : 3500,
  }
  listeners.forEach((listener) => listener(payload))
}

export function subscribeToToasts(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
