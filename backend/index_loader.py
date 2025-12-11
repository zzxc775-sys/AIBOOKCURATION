# index_loader.py
import os
import io
import zipfile
from typing import Optional

import requests


def ensure_faiss_index(index_dir: str) -> None:
    """
    - index_dir 아래에 index.faiss 가 있으면 아무 것도 안 함
    - 없으면 FAISS_ZIP_URL 에서 zip을 받아서 압축을 해제
    - zip 안에는 faiss_index/ 폴더가 최상단에 있어야 한다.
    """
    index_file = os.path.join(index_dir, "index.faiss")
    if os.path.exists(index_file):
        # 이미 인덱스 있음
        return

    zip_url: Optional[str] = os.getenv("FAISS_ZIP_URL")
    if not zip_url:
        raise RuntimeError(
            "FAISS 인덱스가 없고, 환경변수 FAISS_ZIP_URL 도 설정되어 있지 않습니다."
        )

    # index_dir의 부모 폴더 (예: backend/models)
    root_dir = os.path.dirname(index_dir)
    os.makedirs(root_dir, exist_ok=True)

    print(f"[FAISS] 인덱스가 없어 {zip_url} 에서 zip 다운로드를 시작합니다...")

    resp = requests.get(zip_url)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        # zip 안에 faiss_index/ 폴더가 들어있다고 가정
        zf.extractall(root_dir)

    if not os.path.exists(index_file):
        raise RuntimeError(
            f"[FAISS] zip을 풀었지만 {index_file} 를 찾지 못했습니다. "
            "zip 내부 구조를 확인하세요 (faiss_index/ 폴더 포함 여부)."
        )

    print(f"[FAISS] 인덱스 다운로드 및 압축 해제 완료: {index_dir}")
