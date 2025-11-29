# build_index.py
import os
from core.retriever import BookIndexer

if __name__ == "__main__":
    CSV_PATH = "data/books_with_descriptions.csv"  # ← 8만 건 CSV
    INDEX_DIR = "models/faiss_index"               # 저장 폴더(두 파일 생성)

    os.makedirs(INDEX_DIR, exist_ok=True)

    indexer = BookIndexer(
        model_name="intfloat/multilingual-e5-base",
        device="cpu",
        normalize=True,
    )
    indexer.build_index_from_csv(
        csv_path=CSV_PATH,
        index_dir=INDEX_DIR,
        batch_size=2048,    # 메모리 여유 없으면 1024/512로 낮추세요
        verbose=True,
    )
