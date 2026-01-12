"""
core/retriever_v2.py
- 서버(FASTAPI)에서 사용할 v2 retriever
- LangChain 없이:
  1) SentenceTransformer로 쿼리만 임베딩
  2) faiss.read_index + index.search
  3) 결과 id(row_id)로 meta.parquet에서 행을 뽑아 반환

이 파일은 기존 core/retriever.py를 "대체"가 아니라 "추가"로 두는 걸 추천.
(안전하게 BookRetrieverV2로 스위치만 바꿀 수 있게)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import numpy as np
import pandas as pd
import faiss
from sentence_transformers import SentenceTransformer


@dataclass
class RetrieverV2Config:
    index_dir: str = "models/faiss_index_v2"
    model_name: str = "intfloat/multilingual-e5-base"
    device: str = "cpu"
    # meta 파일명 고정
    index_filename: str = "index.faiss"
    meta_filename: str = "meta.parquet"


class BookRetrieverV2:
    """
    v2 Retriever:
    - normalize_embeddings=True + IndexFlatL2 조합
      => L2^2 = 2 - 2cos (단위벡터 가정)
      => cos = 1 - (dist / 2)
    """

    def __init__(
        self,
        index_dir: str = "models/faiss_index_v2",
        model_name: str = "intfloat/multilingual-e5-base",
        device: str = "cpu",
    ):
        self.cfg = RetrieverV2Config(index_dir=index_dir, model_name=model_name, device=device)

        base = Path(self.cfg.index_dir)
        self.index_path = base / self.cfg.index_filename
        self.meta_path = base / self.cfg.meta_filename

        if not self.index_path.exists():
            raise FileNotFoundError(f"FAISS 인덱스 파일이 없습니다: {self.index_path}")
        if not self.meta_path.exists():
            raise FileNotFoundError(f"메타 파일이 없습니다: {self.meta_path}")

        # 1) 모델 로드
        self.model = SentenceTransformer(self.cfg.model_name, device=self.cfg.device)

        # 2) FAISS 로드
        self.index = faiss.read_index(str(self.index_path))

        # 3) meta 로드 (서버에서는 한 번만 로드해서 메모리에 들고있는게 빠름)
        self.meta = pd.read_parquet(self.meta_path)

        # row_id 무결성 체크 (필수)
        if "row_id" not in self.meta.columns:
            raise ValueError("meta.parquet에 row_id 컬럼이 없습니다. build_index_v2.py가 정상 실행됐는지 확인하세요.")

        # 빠른 조회를 위해 row_id를 인덱스로 세팅 (0..N-1)
        self.meta = self.meta.set_index("row_id", drop=False)

        # FAISS ntotal과 meta row 수가 맞는지 점검
        if int(self.index.ntotal) != int(len(self.meta)):
            # 꼭 1:1이 아니게 설계할 수도 있지만, 지금은 1:1을 전제로 함
            raise ValueError(
                f"FAISS ntotal({self.index.ntotal}) != meta rows({len(self.meta)}). "
                "인덱스/메타가 서로 다른 버전일 가능성이 큽니다."
            )

    @staticmethod
    def _cosine_from_l2_squared(dist: float) -> float:
        # dist = squared L2 distance between normalized vectors
        # dist = 2 - 2cos  => cos = 1 - dist/2
        cos = 1.0 - float(dist) / 2.0
        # 안전 클램프
        return max(0.0, min(1.0, cos))

    def _embed_query(self, query: str) -> np.ndarray:
        qtext = f"query: {query}"
        vec = self.model.encode(
            [qtext],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype(np.float32)
        return vec  # shape (1, dim)

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        if not query or not query.strip():
            return []
        top_k = int(top_k)
        if top_k <= 0:
            return []

        qvec = self._embed_query(query)

        # FAISS search
        # D: squared L2 distances, I: indices(row_id)
        D, I = self.index.search(qvec, top_k)  # shapes: (1, k)
        dists = D[0].tolist()
        ids = I[0].tolist()

        results: List[Dict] = []
        for rank, (row_id, dist) in enumerate(zip(ids, dists), start=1):
            if row_id < 0:
                continue

            row = self.meta.loc[int(row_id)]
            score = self._cosine_from_l2_squared(dist)

            results.append(
                {
                    "id": str(int(row_id)),  # 프론트/서버 호환용
                    "title": str(row.get("title", "")),
                    "author": str(row.get("author", "")) if row.get("author") is not None else None,
                    "description": str(row.get("description", "")) if row.get("description") is not None else None,
                    "content": str(row.get("description", "")) if row.get("description") is not None else None,

                    # 디버깅/랭킹 정보
                    "rank": rank,
                    "score": round(float(score), 6),     # cos(0~1)
                    "score_pct": int(round(score * 100)),
                    "distance": float(dist),             # squared L2 (단위벡터 기준)
                }
            )

        # score 기준 내림차순
        results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return results
