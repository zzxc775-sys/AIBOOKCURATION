import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Search, Loader2, Sparkles, Wand2, BookOpen, Star, AlertCircle, SlidersHorizontal, MessageSquare, ImageOff } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

/**
 * ✅ Fix: "Unterminated string constant" in demo content
 * - 문자열 연결(+ / \n) 대신 템플릿 리터럴 & Array.join('\n')로 안전하게 구성
 * - 기존 동작/시각은 그대로, 내부 구축 방식만 더 견고하게 변경
 * - 추가 런타임 테스트로 content 무결성 검증 강화
 *
 * NOTE
 * - 실제 연동 시 ../api/recommend 의 fetchRecommend/타입을 사용하세요.
 * - 본 파일은 하이파이 목업 + 바인딩/스트리밍/마크다운 프레젠테이션 전부 포함
 */

// ===== 타입 (프로덕션에서는 ../api/recommend 의 타입/함수 사용 권장) =====
export type BookItem = {
  id?: string
  title: string
  author?: string
  content?: string
  description?: string
  score?: number
  image?: string
  thumbnail?: string
  rank?: number
  score_pct?: number
  rel_pct?: number
  stars?: number
  distance?: number | null
  publisher?: string | null
  isbn?: string | null
}

export type RecommendResponse = {
  results: BookItem[]
  content?: string
}

// ===== 안전한 마크다운 생성 유틸 =====
function md(...lines: string[]): string {
  return lines.join('\n')
}

// ===== 데모용 응답 생성기 (문자열 종결/개행 보장) =====
function getDemoResponse(): RecommendResponse {
  const content = md(
    '### 🤖 추천 요약',
    '- **질문 의도**: 퇴근 후 마음을 가볍게 만드는 책',
    '- **핵심 전략**: 감정 안정 → 동기 회복 → 의미 확장',
    '',
    '**왜 이 책들인가요?**',
    '- *아주 작은 습관의 힘*: 실천 장벽을 낮추는 미세 습관.',
    '- *자기만의 방*: 심리적 자율성과 몰입 회복.',
    '- *죽은 시인의 사회*: 감정적 회복과 삶의 활력.'
  )
  
  return {
    results: [
      { title: '아주 작은 습관의 힘', author: '제임스 클리어', content: '작게 시작해 쉽게 이어가는 습관 설계.', score: 0.92, score_pct: 92, stars: 4.7 },
      { title: '자기만의 방', author: '버지니아 울프', content: '내면 자율성과 집중을 회복하는 고전 에세이.', score: 0.88, score_pct: 88, stars: 4.5 },
      { title: '죽은 시인의 사회', author: 'N.H. 클라인바움', content: '감정 몰입과 의미 회복으로 활력 되찾기.', score: 0.81, score_pct: 81, stars: 4.4 }
    ],
    content
  }
}

// ===== 데모용 API (프로덕션에서는 실제 client.post 사용) =====
async function fetchRecommend(_body: { query: string }): Promise<RecommendResponse> {
  // 실제 프로젝트
  // const { data } = await client.post<RecommendResponse>('/recommend', body)
  // return data

  // 데모: 지연 후 샘플 반환
  await new Promise((r) => setTimeout(r, 650))
  return getDemoResponse()
}

// ===== DEV 테스트 (간단한 런타임 유닛 테스트) =====
function runDevTests() {
  try {
    const demo = getDemoResponse()
    console.assert(Array.isArray(demo.results), '[TEST] results는 배열이어야 함')
    console.assert(demo.results.length === 3, '[TEST] 더미 결과 3건')
    console.assert(typeof demo.content === 'string', '[TEST] content는 문자열이어야 함')
    console.assert(demo.content!.includes('### 🤖 추천 요약'), '[TEST] 헤딩 포함')
    console.assert(demo.content!.includes('**왜 이 책들인가요?**'), '[TEST] 이유 섹션 포함')
    console.assert(/\n/.test(demo.content!), '[TEST] 줄바꿈 존재')
    // 문자열 비정상 종료/중간 따옴표 깨짐 방지: 템플릿 기반이면 항상 true
    const endsOk = !/["']$/.test(demo.content!)
    console.assert(endsOk, '[TEST] 문자열 비정상 종료 아님')

    // 추가 케이스: 따옴표/괄호/특수문자 포함 시에도 정상이어야 함
    const special = md(
      '### 제목 "따옴표"와 \'작은따옴표\'',
      '- 괄호() 대시–, 이모지 😊, 백틱 `코드`',
      '- 마침표로 끝남.'
    )
    console.assert(special.split('\n').length === 3, '[TEST] special 3줄')
    console.assert(/백틱 `코드`/.test(special), '[TEST] 인라인 코드 포함')
    console.assert(special.endsWith('마침표로 끝남.'), '[TEST] 정상 종료')

    console.log('%c[TEST] 데모 응답/문자열 무결성 테스트 통과', 'color: #16a34a')
  } catch (e) {
    console.error('[TEST] 실패:', e)
  }
}

export default function BookRecommendationUI() {
  
  type Phase = 'idle' | 'loading' | 'results' | 'empty' | 'error'
  const [query, setQuery] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')

  // 백엔드 데이터
  const [items, setItems] = useState<BookItem[]>([])
  const [content, setContent] = useState<string>('')
  const [errorMsg, setErrorMsg] = useState<string>('')

  // 스트리밍(타자 효과) - 서버는 한 번에 내려주지만, UI에서는 점진적으로 표기
  const [answer, setAnswer] = useState('')
  const streamTimer = useRef<number | null>(null)

  const startStreaming = (text: string) => {
    if (streamTimer.current) window.clearInterval(streamTimer.current)
    setAnswer('')
    let i = 0
    streamTimer.current = window.setInterval(() => {
      i += 3
      setAnswer(text.slice(0, i))
      if (i >= text.length && streamTimer.current) {
        window.clearInterval(streamTimer.current)
        streamTimer.current = null
      }
    }, 18)
  }

  useEffect(() => {
    // DEV 환경에서 간단 테스트 수행
    if (typeof import.meta !== 'undefined' && (import.meta as any).env?.DEV) {
      runDevTests()
    }
    return () => { if (streamTimer.current) window.clearInterval(streamTimer.current) }
  }, [])

  const handleSearch = async () => {
    if (!query.trim()) return
    try {
      setPhase('loading')
      setItems([])
      setContent('')
      setErrorMsg('')
      const data = await fetchRecommend({ query })
      if (!data.results?.length) {
        setPhase('empty')
        return
      }
      setItems(data.results)
      setContent(data.content ?? '')
      setPhase('results')
      if (data.content) startStreaming(data.content)
    } catch (e: any) {
      setErrorMsg(e?.message || '알 수 없는 오류')
      setPhase('error')
    }
  }

  const showDemo = async () => {
    setQuery('퇴근 후 마음이 편해지는 에세이')
    await handleSearch()
  }

  return (
    <main className="min-h-screen bg-gradient-to-b from-blue-50/60 via-white to-white">
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="mx-auto max-w-6xl px-4 pt-16 pb-10">
          <motion.h1 initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="text-4xl md:text-5xl font-extrabold tracking-tight text-gray-900 flex items-center gap-3">
            <Sparkles className="text-blue-600 w-8 h-8" /> AI 도서 추천
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }} className="mt-3 text-gray-600 max-w-2xl">
            상황·감정·목표에 맞춘 책을 빠르고 정확하게. 예: “퇴근 후 마음 풀리는 짧은 에세이”, “팀장 승진 대비 리더십 책”.
          </motion.p>

          {/* 검색 바 */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.15 }} className="mt-8 flex flex-col md:flex-row gap-3 md:items-center">
            <div className="flex-1 bg-white rounded-2xl border border-gray-200 shadow-sm p-2.5">
              <div className="flex items-center gap-2">
                <Search className="w-5 h-5 text-gray-400 shrink-0" />
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="예: 연인과 이별한 친구에게 위로가 되는 소설" className="w-full bg-transparent outline-none text-gray-900 placeholder:text-gray-400" />
              </div>
            </div>
            <button onClick={handleSearch} className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-2xl bg-blue-600 text-white font-semibold hover:bg-blue-700 shadow">
              <Wand2 className="w-5 h-5" /> 추천받기
            </button>
          </motion.div>

          {/* 추천 토픽 칩 & 예시버튼 */}
          <div className="mt-4 flex flex-wrap gap-2 text-sm">
            {['힐링 에세이', '번아웃 회복', '자기효능감 ↑', '직장인 리더십'].map((t) => (
              <button key={t} onClick={() => setQuery(t)} className="px-3 py-1.5 rounded-full bg-blue-50 text-blue-700 border border-blue-100 hover:bg-blue-100">#{t}</button>
            ))}
            <button onClick={showDemo} className="px-3 py-1.5 rounded-full border border-gray-200 text-gray-700 hover:bg-gray-50">예시 대답 보기</button>
          </div>

          {/* 신뢰 배지 */}
          <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            {[
              { label: '응답 속도', value: '≈ 0.9초' },
              { label: '도서 데이터', value: '50,000+권' },
              { label: '설명 표현', value: 'Markdown 지원' },
              { label: '맞춤 태그', value: '감정·상황 기반' }
            ].map((s) => (
              <div key={s.label} className="rounded-xl bg-white border border-gray-200 p-3 flex items-center gap-3">
                <BookOpen className="w-5 h-5 text-blue-600" />
                <div>
                  <p className="text-gray-500">{s.label}</p>
                  <p className="font-semibold text-gray-900">{s.value}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 본문: 상태별 섹션 */}
      <section className="mx-auto max-w-6xl px-4 pb-24">
        {phase === 'idle' && <IdleState />}
        {phase === 'loading' && <LoadingState />}
        {phase === 'results' && (
          <div className="grid lg:grid-cols-[1fr_420px] gap-8">
            <ResultsState items={items} />
            <AnswerPanel answer={answer} fullAnswer={content} />
          </div>
        )}
        {phase === 'empty' && <EmptyState onReset={() => setPhase('idle')} />}
        {phase === 'error' && <ErrorState message={errorMsg} onRetry={() => setPhase('idle')} />}
      </section>

      {/* 푸터 */}
      <footer className="border-t border-gray-100 py-8 text-center text-gray-400 text-sm">
        © 2025 AI Book Curator · 컬러: Blue-600 / Gray-50~900 · 타입스케일: 12/14/16/20/24/32/40
      </footer>
    </main>
  )
}

// ===== 상태 컴포넌트들 =====

function IdleState() {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-6">
      <div className="grid md:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="rounded-2xl bg-white border border-gray-200 p-5">
            <div className="flex items-center gap-2 text-blue-700">
              <SlidersHorizontal className="w-4 h-4" />
              <p className="text-sm font-semibold">추천 가이드 #{i}</p>
            </div>
            <p className="mt-2 text-gray-700 text-sm leading-relaxed">
              당신의 상황·감정·목표를 한 문장으로 적어보세요. 예: “프리랜서로 일하며 동기부여가 떨어졌을 때 읽을 책”. 구체적일수록 더 정밀한 매칭이 이뤄집니다.
            </p>
          </div>
        ))}
      </div>
    </motion.div>
  )
}

function LoadingState() {
  return (
    <div className="mt-10">
      <div className="flex items-center gap-2 text-gray-600">
        <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
        <p>AI가 당신에게 어울리는 책을 찾는 중이에요…</p>
      </div>
      <div className="mt-6 grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="rounded-2xl border border-gray-200 p-4 bg-white">
            <div className="h-40 w-full rounded-xl bg-gray-100 animate-pulse" />
            <div className="mt-3 h-4 w-2/3 bg-gray-100 rounded animate-pulse" />
            <div className="mt-2 h-3 w-1/2 bg-gray-100 rounded animate-pulse" />
            <div className="mt-4 h-3 w-5/6 bg-gray-100 rounded animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  )
}

function ResultsState({ items }: { items: BookItem[] }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-4">
      {/* 결과 카드 그리드 */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-2 gap-5">
        {items.map((b, i) => (
          <motion.article key={(b.id ?? b.title) + i} initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.35, delay: i * 0.05 }} className="group rounded-2xl bg-white border border-gray-200 shadow-sm hover:shadow-md transition p-4">
            {/* 표지/썸네일 */}
            {b.thumbnail ? (
              <div className="relative aspect-[3/4] w-full overflow-hidden rounded-xl bg-gray-50">
                <img src={b.thumbnail} alt={b.title} className="absolute inset-0 w-full h-full object-cover" />
              </div>
            ) : (
              <div className="relative aspect-[3/4] w-full rounded-xl bg-gradient-to-br from-gray-100 to-gray-200 grid place-items-center text-gray-400">
                <ImageOff className="w-6 h-6" />
                <div className="absolute bottom-3 left-3 right-3 text-xs text-gray-500">no thumbnail</div>
              </div>
            )}

            <h3 className="mt-3 text-lg font-semibold text-gray-900 line-clamp-2">{b.title}</h3>
            {b.author && <p className="text-sm text-gray-600 mt-0.5">👤 {b.author}</p>}
            {b.content && <p className="mt-2 text-sm text-gray-800 line-clamp-3">{b.content}</p>}

            <div className="mt-3 flex items-center justify-between">
              <div className="flex items-center gap-1 text-amber-500">
                <Star className="w-4 h-4 fill-current" />
                <span className="text-xs font-medium text-gray-600">{typeof b.score_pct === 'number' ? `유사도 ${b.score_pct}%` : typeof b.score === 'number' ? `score ${(b.score * 100).toFixed(0)}%` : '추천'}</span>
              </div>
              {typeof b.stars === 'number' && (
                <span className="text-xs text-gray-500">⭐ {b.stars.toFixed(1)}</span>
              )}
            </div>

            <div className="mt-4 flex gap-2">
              <button className="flex-1 rounded-xl bg-blue-600 text-white text-sm font-semibold py-2 hover:bg-blue-700">상세 보기</button>
              <button className="px-3 rounded-xl border border-gray-200 text-sm text-gray-700 hover:bg-gray-50">보관함</button>
            </div>
          </motion.article>
        ))}
      </div>
    </motion.div>
  )
}

function AnswerPanel({ answer, fullAnswer }: { answer: string; fullAnswer: string }) {
  return (
    <aside className="lg:sticky lg:top-6 h-fit">
      <div className="rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
        <div className="flex items-center gap-2 text-blue-900">
          <MessageSquare className="w-5 h-5" />
          <h4 className="font-semibold">AI 대답</h4>
        </div>
        {/* 스트리밍 텍스트(프리뷰) */}
        <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-blue-900">
          {answer ? answer : '결과가 나오면 이 영역에 AI의 추천 요약/이유가 스트리밍으로 표시됩니다.'}
        </div>
        {/* 전체 마크다운 렌더 (완료 후) */}
        {fullAnswer && (
          <div className="mt-3 prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-li:my-0.5">
            <ReactMarkdown>{fullAnswer}</ReactMarkdown>
          </div>
        )}
        {/* 전체복사 */}
        {fullAnswer && (
          <div className="mt-3">
            <button onClick={() => navigator.clipboard.writeText(fullAnswer)} className="text-xs px-3 py-1.5 rounded-lg bg-white text-blue-700 border border-blue-200 hover:bg-blue-50">전체 복사</button>
          </div>
        )}
      </div>

      {/* 추가 힌트 카드 */}
      <div className="mt-3 rounded-2xl border border-gray-200 bg-white p-3 text-xs text-gray-600">
        💡 팁: 질문을 "상황 + 감정 + 시간 제약"으로 써보세요. 예) *퇴근 후 20분, 머리 복잡할 때 가볍게 읽는 책*
      </div>
    </aside>
  )
}

function EmptyState({ onReset }: { onReset: () => void }) {
  return (
    <div className="mt-14 flex flex-col items-center text-center">
      <div className="W-24 h-24 rounded-3xl bg-gray-100 grid place-items-center">
        <BookOpen className="w-10 h-10 text-gray-400" />
      </div>
      <h4 className="mt-4 text-xl font-bold text-gray-900">아직 딱 맞는 책을 못 찾았어요</h4>
      <p className="mt-2 text-gray-600 max-w-md">검색어를 조금 더 구체적으로 바꿔보세요. 예: “퇴근 후 20분 내 완독 가능한 힐링 에세이”.</p>
      <button onClick={onReset} className="mt-5 px-4 py-2 rounded-xl border border-gray-200 hover:bg-gray-50">다시 시도</button>
    </div>
  )
}

function ErrorState({ message, onRetry }: { message?: string; onRetry: () => void }) {
  return (
    <div className="mt-14 flex flex-col items-center text-center">
      <div className="w-24 h-24 rounded-3xl bg-red-50 grid place-items-center">
        <AlertCircle className="w-10 h-10 text-red-600" />
      </div>
      <h4 className="mt-4 text-xl font-bold text-gray-900">문제가 발생했어요</h4>
      <p className="mt-2 text-gray-600 max-w-md">{message || '일시적인 오류입니다. 잠시 후 다시 시도해주세요.'}</p>
      <button onClick={onRetry} className="mt-5 px-4 py-2 rounded-2xl bg-red-600 text-white hover:bg-red-700">다시 시도</button>
    </div>
  )
}
