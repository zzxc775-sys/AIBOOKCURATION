import { useEffect, useRef, useState } from "react"
import BookCard from "../components/BookCard"
import { fetchRecommend, fetchSummary, type SummaryBook } from "../types/api"


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

  // 👇 컴포넌트 내부에서
  const activeReqIdRef = useRef<string | null>(null);
  const summaryAbortRef = useRef<AbortController | null>(null);


  // 새 메시지가 들어올 때마다 스크롤 맨 아래로
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight
    }
  }, [messages])

  // 공통 전송 핸들러 (랜딩/채팅에서 모두 사용)
  const handleSend = async () => {
    const q = input.trim();
    if (!q || isSending) return;
  
    // ✅ GA 이벤트 추가
    if (typeof window !== 'undefined' && (window as any).gtag) {
      (window as any).gtag('event', 'search', {
        search_term: q
      })
    }

    // 0) 이전 summary 요청 취소 (연속 검색시 레이스 방지)
    summaryAbortRef.current?.abort();
    summaryAbortRef.current = null;
  
    // 1) 랜딩 → 채팅 화면 전환 (첫 메시지일 때)
    if (mode === "landing") setMode("chat");
  
    setInput("");
  
    // 2) 유저/어시스턴트 메시지 추가
    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();
  
    // 이번 요청의 고유 ID (요약 응답이 늦게 와도 매칭 체크)
    const reqId = crypto.randomUUID();
    activeReqIdRef.current = reqId;
  
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: q },
      {
        id: assistantId,
        role: "assistant",
        content: "추천 결과를 불러오는 중…",
        isStreaming: true,
      },
    ]);
  
    setIsSending(true);
  
    try {
      // 3) 1차: 추천(검색)
      const res = await fetchRecommend(q, 5);
  
      // ✅ 결과 이벤트
      if (typeof window !== 'undefined' && (window as any).gtag) {
        (window as any).gtag('event', 'view_results', {
          search_term: q,
          result_count: res.results?.length || 0
        })
      }

      // 추천 결과 반영
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                isStreaming: false,
                content: "추천 이유 생성 중…",
                books: res.results ?? [],
              }
            : m
        )
      );
  
      // 4) 2차: 요약(LLM) - top3만 최소 payload로
      const top3: SummaryBook[] = (res.results ?? []).slice(0, 3).map((b, idx) => {
        const text = (b.description ?? b.content ?? "").trim().replace(/\s+/g, " ");
        const snippet = text.length > 80 ? text.slice(0, 80) + "..." : text;
        return {
          title: b.title,
          author: b.author,
          snippet,
          rank: idx + 1,
          score_pct: (b as any).score_pct,
        };
      });
  
      // books가 없으면 summary 호출할 필요 없음
      if (top3.length === 0) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: "추천할 도서를 찾지 못했어요. 다른 키워드로 다시 시도해 주세요." }
              : m
          )
        );
        return;
      }
  
      // AbortController 설정
      const ac = new AbortController();
      summaryAbortRef.current = ac;
  
      fetchSummary(q, top3, ac.signal)
        .then((sum) => {
          // ✅ 레이스 방지: 최신 요청인지 확인
          if (activeReqIdRef.current !== reqId) return;
  
          const text = (sum.content ?? "").trim();
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: text || "추천 이유를 생성하지 못했어요." }
                : m
            )
          );
        })
        .catch((e: any) => {
          // Abort는 조용히 무시 (새 요청이 온 정상 케이스)
          if (e?.name === "AbortError") return;
  
          // ✅ 레이스 방지
          if (activeReqIdRef.current !== reqId) return;
  
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: "추천 이유 생성이 지연되고 있어요. 잠시 후 다시 시도해 주세요." }
                : m
            )
          );
        })
        .finally(() => {
          if (summaryAbortRef.current === ac) {
            summaryAbortRef.current = null;
          }
        });
    } catch (e: any) {
      // recommend 자체 실패
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                isStreaming: false,
                error: e?.message || "추천 생성 중 오류가 발생했어요. 잠시 후 다시 시도해주세요.",
              }
            : m
        )
      );
    } finally {
      setIsSending(false);
    }
  };
  

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


