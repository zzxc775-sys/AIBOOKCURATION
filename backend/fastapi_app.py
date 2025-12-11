# fastapi_app.py (교체/추가 포함 완성본)

import os
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- retriever import (패키지/단일파일 모두 대응) ---
from core.retriever import BookRetriever
from index_loader import ensure_faiss_index
# --- DeepSeekRecommender import (파일명 오타 대응: llm_integration / llm_intergration 둘 다 시도) ---
DeepSeekRecommender = None
try:
    from core.llm_integration import DeepSeekRecommender as _DS
    DeepSeekRecommender = _DS
except ModuleNotFoundError:
    try:
        # 혹시 이전에 'llm_intergration.py' 오타 파일명이 있을 수도 있음
        from core.llm_intergration import DeepSeekRecommender as _DS2
        DeepSeekRecommender = _DS2
    except ModuleNotFoundError:
        pass  # LLM 비활성화 모드로 동작

app = FastAPI(title="AI Book Curation API", version="0.2.0")

# CORS: 프론트(5173) 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 스키마 ----------
class Book(BaseModel):
    id: Optional[str] = Field(None, description="도서 내부 ID")
    title: str
    author: Optional[str] = None
    description: Optional[str] = None  # 백엔드 raw 키가 'description'이면 그대로 전달
    content: Optional[str] = None      # 프론트 BookCard가 content를 쓰면 매핑해서 채울 수 있음
    thumbnail: Optional[str] = None
    rank: Optional[int] = None
    score: Optional[float] = None          # 0~1 코사인
    score_pct: Optional[int] = None        # 0~100%
    rel_pct: Optional[int] = None          # 세트 내 10~100%
    stars: Optional[float] = None          # 0.5~5.0
    distance: Optional[float] = None       # 원시 거리(디버그용)
    publisher: Optional[str] = None
    isbn: Optional[str] = None

class RecommendRequest(BaseModel):
    query: str = Field(..., description="사용자 질의")
    top_k: int = Field(5, ge=1, le=20)
    filters: Optional[Dict] = None

class RecommendResponse(BaseModel):
    query: str
    results: List[Book]
    content: Optional[str] = None  # LLM 요약문(없을 수 있음)

# ---------- 전역 리소스 ----------
_retriever: Optional[BookRetriever] = None
_recommender: Optional[object] = None  # DeepSeekRecommender 인스턴스 또는 None

def _get_index_path() -> str:
    # 기본 경로를 data/faiss_books.index로 가정. 필요시 INDEX_PATH 환경변수로 교체 가능.
    return os.getenv("INDEX_PATH", os.path.join(os.path.dirname(__file__), "models", "faiss_index"))

@app.on_event("startup")
def _startup():
    global _retriever, _recommender
    # 0) 인덱스 경로 계산
    index_path = _get_index_path()

    # 1) 인덱스가 없으면 zip에서 다운로드 + 압축 해제
    ensure_faiss_index(index_path)

    # 2) FAISS 로드
    _retriever = BookRetriever(index_path)

    # 3) DeepSeek 준비(키가 있어야 활성화)
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if DeepSeekRecommender and api_key:
        try:
            _recommender = DeepSeekRecommender(api_key=api_key)
        except Exception:
            _recommender = None  # 실패해도 검색은 가능

@app.get("/")
def root():
    return {
        "name": "AI Book Curation API",
        "docs": "/docs",
        "endpoints": {"health": "/healthz", "recommend": "POST /recommend"},
    }

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query는 비어 있을 수 없습니다.")
    if _retriever is None:
        raise HTTPException(status_code=500, detail="Retriever가 초기화되지 않았습니다.")

    # 1) 임베딩/FAISS 유사도 검색
    try:
        raw_items = _retriever.retrieve(req.query, top_k=req.top_k)  # list[dict] 가정
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류: {e}")

    # 2) 프론트 스키마에 맞게 매핑 (content가 없으면 description을 content로 넣어줌)
    items: List[Book] = []
    for r in (raw_items or []):
        items.append(
            Book(
                id=r.get("id"),
                title=r.get("title", "제목 없음"),
                author=r.get("author"),
                description=r.get("description"),
                content=r.get("content") or r.get("description"),
                thumbnail=r.get("thumbnail"),
                rank=r.get("rank"),
                score=r.get("score"),
                score_pct=r.get("score_pct"),
                rel_pct=r.get("rel_pct"),
                stars=r.get("stars"),
                distance=r.get("distance"),
                publisher=r.get("publisher"),
                isbn=r.get("isbn")
            )
        )

    # 3) (선택) DeepSeek 요약문
    summary = None
    if _recommender is not None and items:
        try:
            # 상위 5권만 프롬프트에 사용 (토큰/속도 절약)
            # 네 클래스 시그니처와 동일하게 사용
            topN = [b.model_dump() for b in items[:5]]
            out = _recommender.generate_recommendation(req.query, topN, model="deepseek-chat")
            summary = out.get("content")
        except Exception:
            summary = None  # LLM 실패해도 결과는 그대로

    return RecommendResponse(query=req.query, results=items, content=summary)
