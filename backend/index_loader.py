import os, zipfile, requests
from pathlib import Path

def ensure_faiss_index(index_dir: str):
    index_dir = Path(index_dir)
    index_file = index_dir / "index.faiss"
    if index_file.exists():
        print("[FAISS] 기존 인덱스 발견. 다운로드 생략.")
        return

    zip_url = os.getenv("FAISS_ZIP_URL")
    if not zip_url:
        raise RuntimeError("FAISS_ZIP_URL 환경변수가 없습니다.")

    index_dir.mkdir(parents=True, exist_ok=True)
    zip_path = index_dir / "faiss_index.zip"

    print(f"[FAISS] 다운로드 시작: {zip_url}")

    # ✅ 스트리밍 다운로드 (RAM 안씀)
    with requests.get(zip_url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB
                if chunk:
                    f.write(chunk)

    print("[FAISS] 압축 해제 시작")

    # ✅ 파일 기반 unzip (RAM 최소)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(index_dir)

    try:
        zip_path.unlink()  # zip 삭제 (디스크 절약)
    except Exception:
        pass

    if not index_file.exists():
        raise RuntimeError(f"[FAISS] 압축 해제 후 {index_file} 없음. zip 내부 경로 확인 필요")

    print("[FAISS] 완료")

def ensure_faiss_index_v2(index_dir: str):
    index_dir = Path(index_dir)
    index_file = index_dir / "index.faiss"
    meta_file = index_dir / "meta.parquet"

    if index_file.exists() and meta_file.exists():
        print("[FAISS_V2] 기존 v2 인덱스 발견. 다운로드 생략.")
        return

    zip_url = os.getenv("FAISS_V2_ZIP_URL")
    if not zip_url:
        raise RuntimeError("FAISS_V2_ZIP_URL 환경변수가 없습니다.")

    index_dir.mkdir(parents=True, exist_ok=True)
    zip_path = index_dir / "faiss_index_v2.zip"

    print(f"[FAISS_V2] 다운로드 시작: {zip_url}")

    with requests.get(zip_url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    print("[FAISS_V2] 압축 해제 시작")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(index_dir)

    try:
        zip_path.unlink()
    except Exception:
        pass

    if not (index_file.exists() and meta_file.exists()):
        raise RuntimeError(
            f"[FAISS_V2] 압축 해제 후 index/meta 없음. "
            f"index={index_file.exists()} meta={meta_file.exists()} "
            f"zip 내부 경로 확인 필요"
        )

    print("[FAISS_V2] 완료")
