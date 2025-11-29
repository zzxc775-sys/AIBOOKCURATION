// src/App.tsx
import { Routes, Route, Navigate, Link } from 'react-router-dom'
import Home from './pages/Home'
import BookRecommendationUI from './pages/BookRecommendationUI'

export default function App() {
  return (
    <main className="min-h-dvh w-screen">
      <nav className="px-4 py-3 border-b bg-white flex gap-3">
        <Link to="/" className="text-blue-600 font-semibold">Home</Link>
        <Link to="/book" className="text-blue-600">Book (new)</Link>
      </nav>

      <div className="p-4">
        <Routes>
          {/* 기본 진입을 기존 홈으로 */}
          <Route path="/" element={<Home />} />
          {/* 새 UI는 /book */}
          <Route path="/book" element={<BookRecommendationUI />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </main>
  )
}


