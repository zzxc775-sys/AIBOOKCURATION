# backend/build_index_from_csv.py
import argparse
import logging
import os
import sys
import time
from pathlib import Path
import traceback
from typing import List, Optional

import pandas as pd
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.schema import Document
from langchain.embeddings.base import Embeddings as BaseEmbeddings

ROOT = Path(__file__).parent
CSV_PATH_DEFAULT = ROOT / "data" / "books_with_descriptions.csv"
OUT_DIR_DEFAULT = ROOT / "models" / "faiss_index"

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("build_index")

# ---------- Progress Wrapper ----------
class ProgressEmbeddings(BaseEmbeddings):
    """
    내부 임베딩을 감싸서 배치 단위 진행률을 로깅.
    """
    def __init__(self, inner: BaseEmbeddings, batch_size: int = 64, sleep: float = 0.0):
        self.inner = inner
        self.batch_size = batch_size
        self.sleep = sleep

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        total = len(texts)
        vectors: List[List[float]] = []
        t0 = time.time()
        logger.info(f"[embed_documents] 전체 {total}개 | 배치 {self.batch_size}개")

        for start in range(0, total, self.batch_size):
            end = min(start + self.batch_size, total)
            batch = texts[start:end]
            b0 = time.time()
            vecs = self.inner.embed_documents(batch)
            vectors.extend(vecs)
            took = time.time() - b0
            elapsed = time.time() - t0
            logger.info(f"  - 진행: {end}/{total} ({end/total:.0%}) | 배치 {len(batch)}개 {took:.1f}s | 누적 {elapsed:.1f}s")
            if self.sleep > 0:
                time.sleep(self.sleep)
        logger.info(f"[embed_documents] 완료 | 총 소요 {time.time()-t0:.1f}s")
        return vectors

    def embed_query(self, text: str) -> List[float]:
        return self.inner.embed_query(text)

# ---------- Utils ----------
def load_books_df(csv_path: Path) -> pd.DataFrame:
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        if len(df) == 0:
            logger.warning(f"CSV는 존재하지만 비어 있습니다: {csv_path}")
        else:
            logger.info(f"CSV 로드: {csv_path} (rows={len(df)}, cols={list(df.columns)})")
        return df

    logger.warning(f"CSV가 없어 더미 데이터로 진행합니다: {csv_path}")
    return pd.DataFrame([
        {"title":"마스터 알고리즘","author":"Pedro Domingos","description":"머신러닝 큰 그림"},
        {"title":"혼공머신러닝+딥러닝","author":"박해선","description":"초보자 실습서"},
        {"title":"밑바닥부터 시작하는 딥러닝","author":"사이토 고키","description":"구현으로 배우는 DL"},
    ])

def to_documents(df: pd.DataFrame) -> List[Document]:
    def pick(cands):
        for c in cands:
            if c in df.columns:
                return c
        return None
    tcol = pick(["title","도서명"]) or "title"
    acol = pick(["author","저자"])
    dcol = pick(["description","desc","summary","요약","설명"])

    docs: List[Document] = []
    for _, r in df.iterrows():
        title = str(r.get(tcol,"") or "")
        author= str(r.get(acol,"") or "") if acol else ""
        desc  = str(r.get(dcol,"") or "") if dcol else ""
        text  = f"passage: 제목: {title}"
        if author: text += f" / 저자: {author}"
        if desc:   text += f"\n설명: {desc}"
        docs.append(Document(
            page_content=text,
            metadata={"title":title or None, "author":author or None, "description":desc or None}
        ))
    return docs

def ensure_outdir(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"출력 폴더 준비 완료: {out_dir}")

def files_exist(out_dir: Path) -> bool:
    required = ["index.faiss", "index.pkl", "docstore.pkl"]
    exists = [ (out_dir / f).exists() for f in required ]
    for f, ok in zip(required, exists):
        logger.info(f"  - {f}: {'OK' if ok else '없음'}")
    return all(exists)

# ---------- Main ----------
def main(
    csv_path: Path,
    out_dir: Path,
    model_name: str = "intfloat/multilingual-e5-base",
    device: str = "cpu",
    normalize: bool = True,
    batch_size: int = 64,
    max_rows: Optional[int] = None
):
    logger.info("=== FAISS 인덱스 빌드 시작 ===")
    logger.info(f"CSV: {csv_path}")
    logger.info(f"OUT: {out_dir}")
    logger.info(f"MODEL: {model_name} | DEVICE: {device} | NORM: {normalize} | BATCH: {batch_size}")

    ensure_outdir(out_dir)

    df = load_books_df(csv_path)
    if max_rows is not None:
        df = df.head(max_rows).copy()
        logger.info(f"max_rows={max_rows}로 제한하여 진행합니다. (rows={len(df)})")

    docs = to_documents(df)
    logger.info(f"Document 개수: {len(docs)}")

    # 내부 임베딩 + 진행 표시 래퍼
    base = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": normalize},
    )
    emb = ProgressEmbeddings(base, batch_size=batch_size)

    # 인덱스 만들기 (임베딩 진행률은 emb가 출력)
    t0 = time.time()
    vstore = FAISS.from_documents(docs, emb)
    build_took = time.time() - t0
    logger.info(f"FAISS 빌드 완료: {build_took:.1f}s")

    # 저장
    vstore.save_local(str(out_dir))
    logger.info(f"저장 완료: {out_dir}")

    # 산출물 확인
    ok = files_exist(out_dir)
    if ok:
        logger.info("✅ 모든 산출물 존재(index.faiss, index.pkl, docstore.pkl).")
    else:
        logger.error("❌ 산출물 일부가 없습니다. 위 파일 존재 여부를 확인하세요.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=str, default=str(CSV_PATH_DEFAULT), help="CSV 경로")
    parser.add_argument("--out", type=str, default=str(OUT_DIR_DEFAULT), help="출력 폴더")
    parser.add_argument("--model", type=str, default="intfloat/multilingual-e5-base", help="임베딩 모델")
    parser.add_argument("--device", type=str, default="cpu", help="cpu 또는 cuda")
    parser.add_argument("--batch-size", type=int, default=64, help="임베딩 배치 크기")
    parser.add_argument("--max-rows", type=int, default=None, help="샘플 테스트용 상한 (예: 200)")
    args = parser.parse_args()

    try:
        main(
            csv_path=Path(args.csv),
            out_dir=Path(args.out),
            model_name=args.model,
            device=args.device,
            batch_size=args.batch_size,
            max_rows=args.max_rows,
        )
    except Exception as e:
        logger.error("예외 발생! 스택트레이스를 확인하세요.")
        traceback.print_exc()
        sys.exit(1)
