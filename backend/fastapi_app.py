# fastapi_app.py (교체/추가 포함 완성본)

import os
import time
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- retriever import (v2 팩토리) ---
from core.retriever_factory import get_retriever

# --- v1 인덱스 보장(다운로드/압축해제) ---
from index_loader import ensure_faiss_index, ensure_faiss_index_v2

# --- DeepSeekRecommender import (파일명 오타 대응: llm_integration / llm_intergration 둘 다 시도) ---
DeepSeekRecommender = None
try:
    from core.llm_integration import DeepSeekRecommender as _DS
    DeepSeekRecommender = _DS
except ModuleNotFoundError:
    try:
        # 혹시 이전에 'llm_intergration.py' 오타 파일명이 있을 수도 있음
        from core.llm_integration import DeepSeekRecommender as _DS2
        DeepSeekRecommender = _DS2
    except ModuleNotFoundError:
        DeepSeekRecommender = None
        
app = FastAPI(title="AI Book Curation API", version="0.2.0")

# CORS: 환경변수 기반 (배포/로컬 모두 대응)
cors_env = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
)
origins = [o.strip() for o in cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 스키마 ----------
class Book(BaseModel):
    id: Optional[str] = Field(None, description="도서 내부 ID")
    title: str
    author: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    thumbnail: Optional[str] = None
    rank: Optional[int] = None
    score: Optional[float] = None
    score_pct: Optional[int] = None
    rel_pct: Optional[int] = None
    stars: Optional[float] = None
    distance: Optional[float] = None
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
    debug: Optional[Dict] = None  # ✅ 추가

# ---------- 전역 리소스 ----------
# v1(BookRetriever) 또는 v2(BookRetrieverV2) 모두 들어갈 수 있으니 타입을 넓게 잡음
_retriever: Optional[object] = None
_recommender: Optional[object] = None  # DeepSeekRecommender 인스턴스 또는 None


def _get_index_path() -> str:
    # v1 기본 경로(기존 유지). v2에서는 보통 사용 안 함.
    return os.getenv(
        "INDEX_PATH",
        os.path.join(os.path.dirname(__file__), "models", "faiss_index")
    )


@app.on_event("startup")
def _startup():
    global _retriever, _recommender

    retriever_version = os.getenv("RETRIEVER_VERSION", "v1").lower().strip()

    # -----------------------------
    # (A) Retriever 초기화 (v1/v2 스위칭)
    # -----------------------------
    if retriever_version == "v2":
        # v2: get_retriever()가 BookRetrieverV2를 만들어서 리턴
        # (models/faiss_index_v2/index.faiss + meta.parquet 로딩)
        v2_dir = os.path.join(os.path.dirname(__file__), "models", "faiss_index_v2")
        ensure_faiss_index_v2(v2_dir)   # ✅ 추가: v2 인덱스/메타 준비
        _retriever = get_retriever()
        print("✅ Retriever initialized: v2")

    else:
        # v1: 기존 로직 유지 (zip 다운로드/압축해제 -> pkl 로드)
        index_path = _get_index_path()
        ensure_faiss_index(index_path)

        # v1 retriever는 여기서만 import (v2 쓸 때 불필요 의존성 로딩 방지)
        from core.retriever import BookRetriever
        _retriever = BookRetriever(index_path)
        print("✅ Retriever initialized: v1")

    # -----------------------------
    # (B) DeepSeek 준비(키가 있어야 활성화)
    # -----------------------------
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

    timings = {}
    t0 = time.perf_counter()
    
    # 1) 임베딩/FAISS 유사도 검색
    try:
        t_search0 = time.perf_counter()
        # v1/v2 모두 retrieve(query, top_k) 인터페이스를 맞춘다는 전제
        raw_items = _retriever.retrieve(req.query, top_k=req.top_k)  # type: ignore[attr-defined]
        timings["search_sec"] = round(time.perf_counter() - t_search0, 4)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류: {e}")

    # 2) 프론트 스키마에 맞게 매핑
    t_map0 = time.perf_counter()
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
    timings["map_sec"] = round(time.perf_counter() - t_map0, 4)
    
    def _llm_book_payload(b: Book) -> Dict:
        # LLM에 보낼 최소 정보만 구성 (입력 토큰 절약)
        text = (b.description or b.content or "").strip()
        # 앞부분부터 자르기 (요약/소개는 보통 앞에 핵심이 있음)
        if len(text) > 140:
            text = text[:140] + "..."
        return {
            "title": b.title,
            "author": b.author,
            "snippet": text,
            "score_pct": b.score_pct,
            "score": b.score,
            "rank": b.rank,
        }
    
    # 3) (선택) DeepSeek 요약문
    summary = None
    llm_error = None
    llm_used = False
    
    if _recommender is not None and items:
        try:
            t_llm0 = time.perf_counter()
            topN = [b.model_dump() for b in items[:5]]
            out = _recommender.generate_recommendation(req.query, topN, model="deepseek-chat")
            summary = out.get("content")
            timings["llm_sec"] = round(time.perf_counter() - t_llm0, 4)
        except Exception as e:
            timings["llm_sec"] = round(time.perf_counter() - t_llm0, 4)
            llm_error = str(e)

    timings["total_sec"] = round(time.perf_counter() - t0, 4)
    timings["llm_used"] = llm_used
    if llm_error:
        timings["llm_error"] = llm_error

     # ✅ debug는 환경변수 켰을 때만 내려주기 (운영에서 항상 노출 방지)
    include_debug = os.getenv("INCLUDE_TIMINGS", "0") == "1"
    debug = timings if include_debug else None

    return RecommendResponse(query=req.query, results=items, content=summary, debug=debug)
