import { useEffect, useRef, useState } from 'react'
import { subscribeToToasts } from '../utils/toast'

export default function ToastHost() {
  const [toasts, setToasts] = useState([])
  const timersRef = useRef({})

  useEffect(() => {
    const unsubscribe = subscribeToToasts((toast) => {
      setToasts((prev) => [...prev, toast])
      const timer = window.setTimeout(() => {
        setToasts((prev) => prev.filter((item) => item.id !== toast.id))
        delete timersRef.current[toast.id]
      }, toast.duration)
      timersRef.current[toast.id] = timer
    })

    return () => {
      unsubscribe()
      Object.values(timersRef.current).forEach((timer) => window.clearTimeout(timer))
      timersRef.current = {}
    }
  }, [])

  if (toasts.length === 0) return null

  return (
    <div className="toast-viewport" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.type || 'info'}`}>
          {toast.text}
        </div>
      ))}
    </div>
  )
}
