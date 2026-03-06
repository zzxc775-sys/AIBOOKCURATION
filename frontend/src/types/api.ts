// api.ts (또는 네가 쓰는 API 모듈 파일)
// 백엔드의 베이스 URL을 환경변수에서 읽고, 없으면 로컬 8000으로.
const API_BASE =
  // Vite에서는 env 변수를 import.meta.env.VITE_* 로 읽는다.
  import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

/**
 * 추천 API 호출
 * @param query 사용자의 자연어 질의 (ex: "연애 이별 위로되는 책")
 * @param topK  추천 개수 (기본 5)
 */
export async function fetchRecommend(query: string, topK = 5) {
  // 백엔드의 /recommend 엔드포인트에 POST로 JSON 전송
  const resp = await fetch(`${API_BASE}/recommend`, {
    method: "POST", // FastAPI에서 @app.post("/recommend") 로 받는다
    headers: {
      "Content-Type": "application/json", // JSON 요청임을 알림
    },
    body: JSON.stringify({
      query,       // 서버의 RecommendRequest.query와 매핑
      top_k: topK, // 서버의 RecommendRequest.top_k와 매핑
    }),
  });

  // HTTP 상태코드가 200대가 아니면 에러로 처리
  if (!resp.ok) {
    const text = await resp.text(); // 서버가 보낸 에러 메시지를 읽어서
    throw new Error(`API ${resp.status}: ${text}`); // 디버깅에 도움
  }

  // 성공 시 JSON 파싱
  // 서버의 RecommendResponse(items: Book[]) 스키마를 그대로 따름
  const data = await resp.json();
  return data as {
    query: string;
    results: Array<{
      id?: string;
      title: string;
      author?: string;
      description?: string;
      content?: string;
      thumbnail?: string;
      score?: number;
    }>;
    content?: string;
  };
}

// LLM에 보낼 책 최소 정보 타입 정의
// 백엔드 /summary에서 기대하는 구조와 맞춰야 함
export type SummaryBook = {
  title: string;        // 책 제목 (필수)
  author?: string;      // 저자 (선택)
  snippet?: string;     // 짧은 설명 (LLM 입력 줄이기용)
  score_pct?: number;   // 유사도 점수 퍼센트 (선택)
  rank?: number;        // 몇 번째 추천인지 (선택)
};

// 요약 API 호출 함수
export async function fetchSummary(
  query: string,          // 사용자의 질문
  books: SummaryBook[],   // 상위 3권 정도의 최소 정보
  signal?: AbortSignal    // 요청 취소용 (AbortController)
) {
  // 백엔드 /summary로 POST 요청
  const resp = await fetch(`${API_BASE}/summary`, {
    method: "POST",  // FastAPI @app.post("/summary")
    headers: { 
      "Content-Type": "application/json"  // JSON 전송
    },
    // 서버에서 받는 형식: { query: string, books: [...] }
    body: JSON.stringify({ query, books }),
    signal,  // AbortController 연결 (연속 검색시 이전 요청 취소)
  });

  // HTTP 상태코드가 200이 아니면 에러 처리
  if (!resp.ok) {
    const text = await resp.text();  // 서버 에러 메시지 읽기
    throw new Error(`API ${resp.status}: ${text}`);
  }

  // 성공하면 JSON 파싱
  // 서버 SummaryResponse와 맞춰줌
  return (await resp.json()) as { 
    content?: string | null;  // LLM이 만든 추천 이유
    debug?: any;              // 타이밍/에러 정보 (옵션)
  };
}
