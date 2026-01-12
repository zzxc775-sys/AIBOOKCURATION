"""
build_index_v2.py (메모리 안전 버전)
- 임베딩을 한 번에 전부 모으지 않고, 배치별로 FAISS에 바로 add() 하는 방식(스트리밍)
- meta.parquet는 row_id + (title, author, description)만 저장

실행:
  (PowerShell)
  $env:EMBED_BATCH_SIZE="32"
  $env:MAX_CHARS="1200"
  $env:MAX_SEQ_LEN="256"
  python backend/build_index_v2.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import faiss
from sentence_transformers import SentenceTransformer


# -------------------------
# 경로/설정
# -------------------------
BASE_DIR = Path(__file__).resolve().parent  # backend/
DEFAULT_INPUT = BASE_DIR / "data" / "books_with_descriptions"
OUT_DIR = BASE_DIR / "models" / "faiss_index_v2"

MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "intfloat/multilingual-e5-base")
DEVICE = os.getenv("EMBED_DEVICE", "cpu")

# ✅ 기본값을 안전하게 낮춤 (기존 2048은 CPU에서 터질 확률 높음)
BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "32"))

# ✅ 텍스트 길이 제한 (토큰 폭발 방지)
MAX_CHARS = int(os.getenv("MAX_CHARS", "1200"))

# ✅ 모델 max_seq_length 제한 (토큰 폭발 방지)
MAX_SEQ_LEN = int(os.getenv("MAX_SEQ_LEN", "256"))


def _resolve_input_path(p: Path) -> Path:
    if p.exists() and p.is_file():
        return p

    candidates = [p.with_suffix(".csv"), p.with_suffix(".parquet"), p.with_suffix(".pq")]
    for c in candidates:
        if c.exists() and c.is_file():
            return c

    if p.exists() and p.is_dir():
        for ext in ("*.parquet", "*.pq", "*.csv"):
            files = sorted(p.glob(ext))
            if files:
                return files[0]

    raise FileNotFoundError(f"입력 데이터 파일을 찾을 수 없습니다: {p} (또는 {candidates})")


def _load_dataframe(input_path: Path) -> pd.DataFrame:
    input_path = _resolve_input_path(input_path)

    if input_path.suffix.lower() in (".parquet", ".pq"):
        return pd.read_parquet(input_path)
    if input_path.suffix.lower() == ".csv":
        return pd.read_csv(input_path)

    raise ValueError(f"지원하지 않는 확장자: {input_path.suffix}")


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    required = ["title", "author", "description"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing} / 현재 컬럼: {list(df.columns)}")

    df = df.copy()
    for c in required:
        df[c] = df[c].fillna("").astype(str)

    df = df.reset_index(drop=True)
    df["row_id"] = df.index.astype(np.int64)
    return df[["row_id", "title", "author", "description"]]


def _make_passage_text(title: str, author: str, desc: str) -> str:
    # ✅ 너무 긴 설명은 잘라서 토큰 폭발 방지
    desc = (desc or "")[:MAX_CHARS]

    # E5 passage prefix
    return (
        "passage: "
        f"제목: {title} / 저자: {author}\n"
        f"설명: {desc}"
    )


def build_index_v2(input_path: Path = DEFAULT_INPUT, out_dir: Path = OUT_DIR) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"📥 데이터 로드: {input_path}")
    df = _load_dataframe(input_path)
    print(f"✅ 로드 완료: {len(df):,} rows")

    df_meta = _ensure_columns(df)
    print(f"✅ 메타 정리 완료 (저장 컬럼: {list(df_meta.columns)})")

    print(f"🤖 모델 로드: {MODEL_NAME} / device={DEVICE}")
    model = SentenceTransformer(MODEL_NAME, device=DEVICE)

    # ✅ 모델 시퀀스 길이 제한(가능하면)
    try:
        model.max_seq_length = MAX_SEQ_LEN
        print(f"✅ model.max_seq_length = {MAX_SEQ_LEN}")
    except Exception:
        print("⚠️ model.max_seq_length 설정 실패(모델/버전 차이일 수 있음). 그래도 계속 진행합니다.")

    # 1) 첫 배치로 dim 알아내고 FAISS index 생성
    n = len(df_meta)
    if n == 0:
        raise ValueError("데이터가 비어 있습니다.")

    # 첫 배치 텍스트 준비
    first_end = min(BATCH_SIZE, n)
    first_texts = [
        _make_passage_text(
            df_meta.loc[i, "title"],
            df_meta.loc[i, "author"],
            df_meta.loc[i, "description"],
        )
        for i in range(0, first_end)
    ]

    print("🧠 임베딩 시작… (스트리밍 방식: 배치별로 FAISS에 바로 add)")
    first_emb = model.encode(
        first_texts,
        batch_size=min(BATCH_SIZE, len(first_texts)),
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    ).astype(np.float32)

    dim = int(first_emb.shape[1])
    index = faiss.IndexFlatL2(dim)
    index.add(first_emb)
    print(f"✅ 첫 배치 add 완료: {index.ntotal:,}/{n:,} (dim={dim})")

    # 2) 나머지 배치 반복 (임베딩을 RAM에 쌓지 않음)
    for start in range(first_end, n, BATCH_SIZE):
        end = min(start + BATCH_SIZE, n)

        texts = [
            _make_passage_text(
                df_meta.loc[i, "title"],
                df_meta.loc[i, "author"],
                df_meta.loc[i, "description"],
            )
            for i in range(start, end)
        ]

        emb = model.encode(
            texts,
            batch_size=min(BATCH_SIZE, len(texts)),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype(np.float32)

        index.add(emb)

        if (end % (BATCH_SIZE * 20) == 0) or (end == n):
            print(f"🧱 진행: {end:,}/{n:,} | index.ntotal={index.ntotal:,}")

    print(f"🎉 임베딩/인덱싱 완료: ntotal={index.ntotal:,}")

    # 3) 저장
    index_path = out_dir / "index.faiss"
    meta_path = out_dir / "meta.parquet"

    faiss.write_index(index, str(index_path))
    df_meta.to_parquet(meta_path, index=False)

    print("💾 저장 완료")
    print(f"- {index_path} ({index_path.stat().st_size / (1024*1024):.2f} MB)")
    print(f"- {meta_path} ({meta_path.stat().st_size / (1024*1024):.2f} MB)")
    return index_path, meta_path


if __name__ == "__main__":
    input_env = os.getenv("INPUT_PATH")
    in_path = Path(input_env) if input_env else DEFAULT_INPUT
    build_index_v2(in_path, OUT_DIR)
