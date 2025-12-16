import os
import requests
import zipfile
import io

def ensure_faiss_index(index_dir: str):
    index_file = os.path.join(index_dir, "index.faiss")

    # 이미 존재하면 다운로드 생략
    if os.path.exists(index_file):
        print("[FAISS] 기존 인덱스 발견. 다운로드 생략.")
        return

    zip_url = os.getenv("FAISS_ZIP_URL")
    if not zip_url:
        raise RuntimeError("환경변수 FAISS_ZIP_URL 이 설정되지 않았습니다.")

    print(f"[FAISS] 인덱스 없음 → {zip_url} 에서 다운로드 시작")

    resp = requests.get(zip_url, stream=True)
    if resp.status_code != 200:
        raise RuntimeError(f"FAISS zip 다운로드 실패: {resp.status_code}")

    # zip 읽기
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(index_dir)

    print("[FAISS] 인덱스 다운로드 및 압축 해제 완료")
