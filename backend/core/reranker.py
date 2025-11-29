"""
검색 결과 재정렬을 위한 Cross-Encoder 기반 리랭커
"""

from sentence_transformers import CrossEncoder
from typing import List, Dict

class BookReranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Args:
            model_name: 재랭킹용 Cross-Encoder 모델명
        """
        self.model = CrossEncoder(model_name, max_length=512)

    def rerank(self, query: str, candidates: List[Dict], top_k: int = 3) -> List[Dict]:
        """
        검색 결과 재정렬

        Args:
            query: 원본 검색 쿼리
            candidates: 후보 문서 리스트 (retriever 출력 형식)
            top_k: 최종 반환 결과 수
        
        Returns:
            재정렬된 결과 리스트 (score 업데이트 포함)
        """
        # 크로스 인코딩을 위한 입력 형식 생성
        pairs = [(query, doc["content"]) for doc in candidates]
        
        # 예측 점수 계산
        scores = self.model.predict(pairs)
        
        # 점수 반영 및 정렬
        for doc, score in zip(candidates, scores):
            doc["rerank_score"] = float(score)
        
        # 점수 기준 내림차순 정렬
        sorted_docs = sorted(
            candidates,
            key=lambda x: x["rerank_score"],
            reverse=True
        )[:top_k]
        
        return sorted_docs