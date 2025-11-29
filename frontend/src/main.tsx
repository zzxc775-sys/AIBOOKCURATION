// src/main.tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'  // ✅ 추가
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {/* ✅ 라우팅 컨텍스트 제공자: 여기서 한 번만 앱을 감싸줘야
        App 이하에서 <Routes>/<Link>/<Navigate> 등이 정상 동작함 */}
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
