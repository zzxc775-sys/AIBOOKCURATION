import { useEffect, useRef, useState } from "react"
import BookCard from "../components/BookCard"

/* -----------------------------------------------------------
 * 1) 타입 정의 - 이해를 돕기 위해 파일 안에 간단히 작성
 * ---------------------------------------------------------*/
type BookItem = {
  id?: string
  title: string
  author?: string
  description?: string
  content?: string
  thumbnail?: string
  score?: number
}

type ChatMessage = {
  id: string
  role: "user" | "assistant"
  content: string
  books?: BookItem[]
  isStreaming?: boolean
  error?: string
}

/* -----------------------------------------------------------
 * 2) API 호출 함수 - 백엔드 /recommend 로 POST
 *    - .env 에 VITE_API_BASE_URL 이 없으면 127.0.0.1:8000 사용
 * ---------------------------------------------------------*/
const API_BASE =
  (import.meta as any).env?.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"

async function fetchRecommend(query: string, topK = 5) {
  const resp = await fetch(`${API_BASE}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // 백엔드 RecommendRequest 스키마: { query, top_k }
    body: JSON.stringify({ query, top_k: topK }),
  })
  if (!resp.ok) {
    // 디버깅을 돕기 위해 서버 응답 원문을 에러에 포함
    const text = await resp.text()
    throw new Error(`API ${resp.status}: ${text}`)
  }
  // 기대 응답: { query: string, results: BookItem[], content?: string }
  return (await resp.json()) as {
    query: string
    results: BookItem[]
    content?: string | null
  }
}

/* -----------------------------------------------------------
 * 3) 메인 컴포넌트
 *    - 처음엔 '랜딩 모드' (간단한 인풋 + 버튼)
 *    - 첫 질문 전송 시 '채팅 모드'로 전환하여 이후 대화 누적
 * ---------------------------------------------------------*/
export default function Home() {
  const [mode, setMode] = useState<"landing" | "chat">("landing")
  const [input, setInput] = useState("")
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isSending, setIsSending] = useState(false)
  const threadRef = useRef<HTMLDivElement>(null)

  // 새 메시지가 들어올 때마다 스크롤 맨 아래로
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight
    }
  }, [messages])

  // 공통 전송 핸들러 (랜딩/채팅에서 모두 사용)
  const handleSend = async () => {
    const q = input.trim()
    if (!q || isSending) return

    // 1) 랜딩 → 채팅 화면 전환 (첫 메시지일 때)
    if (mode === "landing") setMode("chat")

    setInput("")

    // 2) 유저 메시지 추가
    const userId = crypto.randomUUID()
    const assistantId = crypto.randomUUID()
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: q },
      {
        id: assistantId,
        role: "assistant",
        content: "", // 곧 채움
        isStreaming: true,
      },
    ])

    // 3) 백엔드 호출
    setIsSending(true)
    try {
      const res = await fetchRecommend(q, 5)

      // 4) 어시스턴트 메시지에 결과/요약 적용
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                isStreaming: false,
                content: res.content ?? "추천 결과를 정리했어요!",
                books: res.results ?? [],
              }
            : m
        )
      )
    } catch (e: any) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                isStreaming: false,
                error:
                  e?.message ||
                  "추천 생성 중 오류가 발생했어요. 잠시 후 다시 시도해주세요.",
              }
            : m
        )
      )
    } finally {
      setIsSending(false)
    }
  }

  // 엔터 전송(Shift+Enter 줄바꿈)
  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  /* ---------------------------------------------------------
   * 4) 랜딩 화면 (간단 검색 → 전송하면 채팅 화면으로 전환)
   * -------------------------------------------------------*/
  if (mode === "landing") {
    return (
      <main className="min-h-dvh w-screen bg-gray-50 grid place-items-center">
        <section className="w-full max-w-xl mx-4 rounded-2xl bg-white shadow-lg p-8 -mt-20">
          <h1 className="text-3xl font-extrabold text-gray-900 text-center">
            📚 AI 도서 추천
          </h1>
          <p className="mt-3 text-center text-gray-600">
            당신의 상황과 취향에 맞는 책을 찾아드릴게요.
          </p>

          <div className="mt-8 flex gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="예: 번아웃이 와서 마음이 지친데, 위로가 되는 산문집 추천해줘"
              className="flex-1 p-3 rounded-xl border border-gray-300 shadow-sm min-h-12 resize-y"
              rows={2}
            />
            <button
              onClick={handleSend}
              disabled={isSending || !input.trim()}
              className="px-5 py-3 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:opacity-50"
            >
              추천받기
            </button>
          </div>

          <p className="mt-3 text-xs text-gray-500 text-center">
            Enter 전송 · Shift+Enter 줄바꿈
          </p>
        </section>
      </main>
    )
  }

  /* ---------------------------------------------------------
   * 5) 채팅 화면 (ChatGPT 형태)
   *    - 왼쪽: 어시스턴트 / 오른쪽: 유저
   *    - 어시스턴트 메시지 아래에 BookCard 목록 표시
   * -------------------------------------------------------*/
  return (
    <div className="h-dvh grid grid-rows-[auto_1fr_auto]">
      {/* 헤더 */}
      <header className="h-14 border-b px-4 flex items-center bg-white">
        <h1 className="font-semibold">AI 도서 추천</h1>
      </header>

      {/* 대화 영역 */}
      <main
        ref={threadRef}
        className="overflow-auto bg-gray-50 px-4 py-6 space-y-6"
      >
        {messages.map((m) => {
          const isUser = m.role === "user"
          return (
            <div
              key={m.id}
              className={`flex ${isUser ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[720px] rounded-2xl px-4 py-3 shadow ${
                  isUser
                    ? "bg-blue-600 text-white"
                    : "bg-white text-gray-900 border border-gray-200"
                }`}
              >
                {/* 메시지 텍스트 */}
                <div className="whitespace-pre-wrap leading-relaxed">
                  {m.content}
                </div>

                {/* 로딩 상태 */}
                {m.isStreaming && (
                  <div className="mt-2 text-xs opacity-60">
                    답변 생성 중…
                  </div>
                )}

                {/* 에러 */}
                {m.error && (
                  <div className="mt-2 text-xs text-red-600">{m.error}</div>
                )}

                {/* 어시스턴트의 추천 카드 목록 */}
                {!isUser && m.books?.length ? (
                  <div className="mt-3 grid gap-3">
                    {m.books.map((b, i) => (
                      <BookCard key={b.id ?? i} book={b} />
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
          )
        })}
      </main>

      {/* 입력창 */}
      <footer className="border-t p-4 bg-white">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            handleSend()
          }}
        >
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="후속 질문을 입력하세요. (Shift+Enter 줄바꿈)"
              className="flex-1 min-h-12 max-h-48 p-3 border rounded-xl resize-y"
              rows={1}
            />
            <button
              type="submit"
              disabled={isSending || !input.trim()}
              className="px-4 py-2 rounded-xl bg-blue-600 text-white disabled:opacity-50"
            >
              보내기
            </button>
          </div>
        </form>
        <p className="mt-2 text-xs text-gray-500">
          Enter 전송 · Shift+Enter 줄바꿈
        </p>
      </footer>
    </div>
  )
}
