# core/retriever.py
# FAISS 인덱스 구축/로드 + 검색 (E5 모델 최적화, 대용량 배치 처리)

from __future__ import annotations
import os
from typing import List, Dict, Optional
from pathlib import Path

import pandas as pd
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.schema import Document

class BookIndexer:
    """
    CSV -> Documents -> FAISS 인덱스 (폴더) 저장
    - E5 모델 권장: 문서에는 'passage:' 접두어, 쿼리에는 'query:' 접두어
    - 대용량(8만+)을 위해 배치로 추가(add_documents) 수행
    """
    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-base",
        device: str = "cpu",
        normalize: bool = True,
    ):
        self.embedding = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": normalize},
        )

    @staticmethod
    def _pick_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
        # 후보 컬럼 중 존재하는 첫 번째를 반환
        for c in candidates:
            if c in df.columns:
                return c
        return None

    def build_index_from_csv(
        self,
        csv_path: str = "data/books_with_descriptions.csv",
        index_dir: str = "models/faiss_index",
        batch_size: int = 2048,
        verbose: bool = True,
    ):
        assert os.path.exists(csv_path), f"CSV not found: {csv_path}"
        os.makedirs(index_dir, exist_ok=True)

        df = pd.read_csv(csv_path)
        if verbose:
            print(f"✅ CSV 로드: {csv_path} / {len(df):,}행")

        # 컬럼 매핑(유연하게 다양한 이름 대응)
        title_col = self._pick_col(df, ["title", "도서명"])
        author_col = self._pick_col(df, ["author", "저자"])
        desc_col = self._pick_col(df, ["description", "desc", "summary", "summery", "설명", "요약"])
        isbn_col = self._pick_col(df, ["isbn", "ISBN", "국제표준도서번호(ISBN)"])
        publisher_col = self._pick_col(df, ["publisher", "출판사"])

        if title_col is None:
            raise ValueError("제목 컬럼을 찾을 수 없습니다. (예: title, 도서명)")
        # author/description/isbn/publisher는 없어도 None으로 처리

        def row_to_doc(row) -> Document:
            title = str(row.get(title_col, "") or "").strip()
            author = str(row.get(author_col, "") or "").strip() if author_col else ""
            desc = str(row.get(desc_col, "") or "").strip() if desc_col else ""
            isbn = str(row.get(isbn_col, "") or "").strip() if isbn_col else ""
            publisher = str(row.get(publisher_col, "") or "").strip() if publisher_col else ""

            text = f"passage: 제목: {title}"
            if author:
                text += f" / 저자: {author}"
            if publisher:
                text += f" / 출판사: {publisher}"
            if desc:
                text += f"\n설명: {desc}"

            meta: Dict[str, str] = {
                "title": title,
                "author": author or None,
                "publisher": publisher or None,
                "isbn": isbn or None,
                "description": desc or None,
            }
            return Document(page_content=text, metadata=meta)

        # 배치로 인덱스 생성/추가
        vector_db: Optional[FAISS] = None
        total = len(df)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            chunk = df.iloc[start:end]
            docs = [row_to_doc(r) for _, r in chunk.iterrows()]

            if vector_db is None:
                vector_db = FAISS.from_documents(docs, self.embedding)
            else:
                vector_db.add_documents(docs)

            if verbose:
                print(f"🧱 배치 추가: {start:,}~{end-1:,} / 누적 {end:,}")

        assert vector_db is not None, "문서가 없습니다."
        vector_db.save_local(index_dir)
        if verbose:
            print(f"🎉 FAISS 인덱스 저장 완료: {index_dir}")

class BookRetriever:
    """
    저장된 FAISS 인덱스(폴더)를 로드해서 검색
    - E5 모델: 쿼리에 'query:' 접두어를 붙인 벡터로 검색
    - 점수는 Relevance Score(0~1)로 반환
    """
    def __init__(
        self,
        index_dir: str = "models/faiss_index",
        model_name: str = "intfloat/multilingual-e5-base",
        device: str = "cpu",
        normalize: bool = True,
    ):
        self.embedding = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": normalize},
        )
        # ❗ 디렉터리 로드 (pkl 포함) -> allow_dangerous_deserialization 필요할 수 있음
        self.vs: FAISS = FAISS.load_local(
            index_dir,
            self.embedding,
            allow_dangerous_deserialization=True
        )

        # core/retriever.py (탐색 함수만 교체)
    def retrieve(self, query: str, top_k: int = 5):
        qtext = f"query: {query}"  # E5 규칙

        # LangChain FAISS: 거리 포함 검색
        pairs = None
        if hasattr(self.vs, "similarity_search_with_score"):
            pairs = self.vs.similarity_search_with_score(qtext, k=top_k)  # [(doc, dist), ...]
        else:
            # 구버전 fallback (점수 없이 문서만)
            docs = self.vs.similarity_search(qtext, k=top_k)
            pairs = [(d, None) for d in docs]

        rows = []
        for doc, dist in pairs:
            # 거리 → 코사인(0~1). (단위벡터 가정: squared_L2 = 2 - 2cos → cos = 1 - d/2)
            if dist is None:
                # fallback: 랭크 기반 대충 값 (최후수단)
                cosine = 1.0
            else:
                cosine = max(0.0, min(1.0, 1.0 - float(dist) / 2.0))
            rows.append((doc, dist, cosine))

        # 상대 정규화(세트 내) + 바닥값(10%)로 0% 방지
        cosines = [c for _, _, c in rows]
        cmax, cmin = (max(cosines) if cosines else 1.0), (min(cosines) if cosines else 0.0)
        eps = 1e-8
        rels = [ (c - cmin) / (cmax - cmin + eps) for c in cosines ]
        rels = [ 0.10 + r * 0.90 for r in rels ]  # 10% ~ 100%

        # 별점: 0.5~5.0, 0.5단위 반올림
        def to_stars(c):
            return max(0.5, round(c * 5 * 2) / 2)

        results = []
        for rank, ((doc, dist, cos), rel) in enumerate(zip(rows, rels), start=1):
            meta = dict(doc.metadata or {})
            results.append({
                "title": meta.get("title") or "",
                "author": meta.get("author"),
                "publisher": meta.get("publisher"),
                "isbn": meta.get("isbn"),
                "content": meta.get("description") or "",
                # --- 여러 점수 지표를 함께 제공 ---
                "rank": rank,                           # 1,2,3…
                "score": round(cos, 3),                 # 코사인(0~1)
                "score_pct": int(round(cos * 100)),     # 0~100%
                "rel_pct": int(round(rel * 100)),       # 10~100% (세트 내)
                "stars": to_stars(cos),                 # 0.5~5.0
                "distance": float(dist) if dist is not None else None,  # 원시 거리(디버깅용)
            })

        # 코사인 기준 내림차순
        return sorted(results, key=lambda x: x["score"], reverse=True)

