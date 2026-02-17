import { Routes, Route } from 'react-router-dom'
import Chat from './pages/Chat'
import Admin from './pages/Admin'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Chat />} />
      <Route path="/admin" element={<Admin />} />
    </Routes>
  )
}

export default App
