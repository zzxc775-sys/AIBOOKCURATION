"""
make_meta_v2.py
- index.faiss는 건드리지 않고 meta.parquet만 생성
"""

from pathlib import Path
import os
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = BASE_DIR / "data" / "books_with_descriptions"
OUT_DIR = BASE_DIR / "models" / "faiss_index_v2"
META_PATH = OUT_DIR / "meta.parquet"


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
    raise FileNotFoundError(f"입력 데이터 파일을 찾을 수 없습니다: {p}")


def main():
    in_path = Path(os.getenv("INPUT_PATH", str(DEFAULT_INPUT)))
    in_path = _resolve_input_path(in_path)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # load
    if in_path.suffix.lower() in (".parquet", ".pq"):
        df = pd.read_parquet(in_path)
    else:
        df = pd.read_csv(in_path)

    # ensure columns
    for c in ["title", "author", "description"]:
        if c not in df.columns:
            raise ValueError(f"필수 컬럼 누락: {c}")
        df[c] = df[c].fillna("").astype(str)

    df = df.reset_index(drop=True)
    df["row_id"] = df.index.astype(np.int64)

    df_meta = df[["row_id", "title", "author", "description"]]
    df_meta.to_parquet(META_PATH, index=False)

    print(f"✅ meta 생성 완료: {META_PATH}")
    print(f"   rows={len(df_meta):,}, size={META_PATH.stat().st_size / (1024*1024):.2f} MB")


if __name__ == "__main__":
    main()
