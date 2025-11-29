from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from core.retriever import BookRetriever
import os

app = FastAPI()

# 요청 모델 정의
class RecommendationRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: dict = None

# 전역 검색 객체
retriever = None

@app.on_event("startup")
def load_retriever():
    global retriever
    index_path = os.path.join(os.path.dirname(__file__), "../models/faiss_index")
    retriever = BookRetriever(index_path)

@app.post("/recommend")
def recommend_books(request: RecommendationRequest):
    try:
        results = retriever.retrieve(
            query=request.query,
            top_k=request.top_k,
            filters=request.filters
        )
        return {"query": request.query, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def health_check():
    return {"status": "ok", "message": "Book Recommendation API"}