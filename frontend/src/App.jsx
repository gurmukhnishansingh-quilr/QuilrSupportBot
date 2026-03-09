import { Routes, Route } from 'react-router-dom'
import Chat from './pages/Chat'
import Admin from './pages/Admin'
import ToastHost from './components/ToastHost'

function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Chat />} />
        <Route path="/admin" element={<Admin />} />
      </Routes>
      <ToastHost />
    </>
  )
}

export default App
