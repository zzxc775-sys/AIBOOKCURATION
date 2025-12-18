# backend/index_loader.py

import os
import requests
import zipfile
import io

def ensure_faiss_index(index_dir: str):
    index_file = os.path.join(index_dir, "index.faiss")

    # 이미 인덱스가 있으면 다운로드 생략
    if os.path.exists(index_file):
        print("[FAISS] 기존 인덱스 발견. 다운로드 생략.")
        return

    zip_url = os.getenv("FAISS_ZIP_URL")
    if not zip_url:
        raise RuntimeError("환경변수 FAISS_ZIP_URL 이 설정되어 있지 않습니다.")

    print(f"[FAISS] 인덱스 없음 → {zip_url} 에서 다운로드 시작")

    resp = requests.get(zip_url, stream=True)
    resp.raise_for_status()

    # 여기서 혹시 HTML을 받으면 바로 알 수 있게 방어 로직 추가
    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type.lower():
        print("[FAISS] 경고: zip 대신 HTML을 받았습니다. URL 또는 권한을 다시 확인하세요.")
        print(resp.text[:300])  # 앞부분만 로그로 표시
        raise RuntimeError("다운로드한 내용이 zip 파일이 아니라 HTML 입니다.")

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(index_dir)

    if not os.path.exists(index_file):
        raise RuntimeError(f"[FAISS] zip을 풀었지만 {index_file} 를 찾지 못했습니다.")

    print("[FAISS] 인덱스 다운로드 및 압축 해제 완료")
