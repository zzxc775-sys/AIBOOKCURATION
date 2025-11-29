import os
import re
import time
import requests
import pandas as pd
from glob import glob
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss

# -------------------------
# 설정
# -------------------------
API_KEY = "acb95e5a2989c1fe3507d7119fb16cf35f331355485bf12f2683eb153ccc1f5e"
headers = {"User-Agent": "Mozilla/5.0"}
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# -------------------------
# 1) 국립중앙도서관 10만 권 단위 누적 수집
# -------------------------
def is_series_volume(title):
    title = title.lower()
    patterns = [
        r"\b\d+\s*권\b", r"제\s*\d+\s*권", r"\bvol\.?\s*\d+",
        r"\bvolume\s*\d+", r"\bbook\s*\d+", r"\bpart\s*\d+",
        r"시즌\s*\d+", r"[\[\(]?\d+\s*권[\]\)]?", r"\s\d{1,2}$", r"[^\d]\d{1,2}$"
    ]
    return any(re.search(p, title) for p in patterns)

def clean_title_prefix(title):
    title = re.sub(r"[\s\(\[].*?\d+.*?[\)\]]", "", title)
    title = re.sub(r"제\s*\d+\s*권", "", title)
    title = re.sub(r"\b\d+\s*권\b", "", title)
    title = re.sub(r"vol\.?\s*\d+", "", title, flags=re.I)
    title = re.sub(r"volume\s*\d+", "", title, flags=re.I)
    title = re.sub(r"book\s*\d+", "", title, flags=re.I)
    title = re.sub(r"\s\d{1,2}$", "", title)
    title = re.sub(r"\d{1,2}$", "", title)
    return title.strip()

def fetch_page(page_no):
    params = {
        "cert_key": API_KEY, "result_style": "json",
        "page_no": page_no, "page_size": 100,
        "sort": "INPUT_DATE", "order_by": "DESC"
    }
    try:
        res = requests.get("https://www.nl.go.kr/seoji/SearchApi.do", params=params, headers=headers, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"❌ 오류 (page {page_no}): {e}")
        return None

def collect_books_incremental():
    collected_file = f"{DATA_DIR}/books_collected.csv"
    existing_df = pd.read_csv(collected_file) if os.path.exists(collected_file) else pd.DataFrame(columns=["title", "author", "isbn"])
    collected_isbns = set(existing_df["isbn"])
    title_prefix_set = set(existing_df["title"].apply(clean_title_prefix)) if not existing_df.empty else set()

      # --- 수정된 부분: last_page.txt로 마지막 페이지 추적 ---
    last_page_file = f"{DATA_DIR}/last_page.txt"
    if os.path.exists(last_page_file):
        with open(last_page_file, "r") as f:
            last_page = int(f.read().strip())
    else:
        last_page = 0  # 첫 실행 시 1페이지부터 시작

    start_page = last_page + 1
    end_page = start_page + 999
    print(f"▶ 국립중앙도서관 데이터 수집: {start_page} ~ {end_page} 페이지 (약 10만 권)")

    new_books = []
    for page_no in range(start_page, end_page + 1):
        data = fetch_page(page_no)
        if not data:
            continue

        for item in data.get("docs", []):
            raw_title = item.get("TITLE", "")
            title = str(raw_title[0]).strip() if isinstance(raw_title, list) else str(raw_title).strip()
            isbn = str(item.get("EA_ISBN", "")).strip()
            author = str(item.get("AUTHOR", "")).strip()
            if not isbn or not title or isbn in collected_isbns:
                continue

            if is_series_volume(title):
                prefix = clean_title_prefix(title)
                if prefix in title_prefix_set:
                    continue
                title_prefix_set.add(prefix)
            else:
                prefix = title.strip()
                if prefix in title_prefix_set:
                    continue
                title_prefix_set.add(prefix)

            new_books.append({"title": title, "author": author, "isbn": isbn})
            collected_isbns.add(isbn)

        print(f"✅ 페이지 {page_no} 완료 / 새로 수집 {len(new_books)}권")

        # 50페이지마다 중간 저장
        if page_no % 50 == 0:
            temp_df = pd.concat([existing_df, pd.DataFrame(new_books)]).drop_duplicates(subset=["isbn"])
            temp_df.to_csv(f"{DATA_DIR}/books_partial_{page_no}.csv", index=False, encoding="utf-8-sig")
            print(f"💾 중간 백업: {DATA_DIR}/books_partial_{page_no}.csv")

        time.sleep(2)

    # 기존 데이터와 합치기
    final_df = pd.concat([existing_df, pd.DataFrame(new_books)]).drop_duplicates(subset=["isbn"])
    final_df.to_csv(collected_file, index=False, encoding="utf-8-sig")
    print(f"📁 누적 도서 데이터: {len(final_df)}권 → {collected_file}")

    # 마지막 페이지 기록 (다음 실행 시 이어서)
    with open(last_page_file, "w") as f:
        f.write(str(end_page))

    return pd.DataFrame(new_books)  # 이번 실행의 신규 도서만 반환

# -------------------------
# 2) Google Books API - 새로 수집한 ISBN만 매칭
# -------------------------
def fetch_google_book_info(isbn):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        if "items" not in data:
            return None
        info = data["items"][0]["volumeInfo"]
        return {
            "title": info.get("title", "").strip(),
            "author": ", ".join(info.get("authors", [])),
            "isbn": isbn,
            "description": info.get("description", "").strip()
        }
    except:
        return None

def match_google_books(new_books_df):
    # 이미 설명이 있는 ISBN 제외
    desc_file = f"{DATA_DIR}/books_with_descriptions.csv"
    existing_desc = pd.read_csv(desc_file) if os.path.exists(desc_file) else pd.DataFrame(columns=["title","author","isbn","description"])
    existing_isbns = set(existing_desc["isbn"])

    target_isbns = [isbn for isbn in new_books_df["isbn"] if isbn not in existing_isbns]
    print(f"▶ Google Books 매칭: 새로 들어온 ISBN {len(target_isbns)}개 처리")

    matched_books = []
    for i, isbn in enumerate(target_isbns, start=1):
        book = fetch_google_book_info(isbn)
        if book and book["description"]:
            matched_books.append(book)
            print(f"✅ [{i}/{len(target_isbns)}] 설명 수집: {book['title']}")
        else:
            print(f"⚠️ [{i}/{len(target_isbns)}] 설명 없음")
        time.sleep(0.4)

    # 기존 설명 데이터와 합치기
    all_desc_df = pd.concat([existing_desc, pd.DataFrame(matched_books)]).drop_duplicates(subset=["isbn"])
    all_desc_df.to_csv(desc_file, index=False, encoding="utf-8-sig")
    print(f"📁 설명 데이터 갱신: 총 {len(all_desc_df)}권 저장")
    return all_desc_df

# -------------------------
# 3) 임베딩 + FAISS 인덱스 생성 (전체 설명 데이터 기준)
# -------------------------
def build_faiss_index(df_desc):
    model = SentenceTransformer("intfloat/multilingual-e5-base")
    texts = (df_desc["title"] + " " + df_desc["author"] + " " + df_desc["description"]).tolist()
    texts = [f"passage: {t}" for t in texts]  # 문서 프리픽스
    embeddings = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=True)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)
    faiss.write_index(index, f"{DATA_DIR}/faiss_books.index")
    df_desc.to_csv(f"{DATA_DIR}/final_books_for_recommendation.csv", index=False, encoding="utf-8-sig")
    print(f"📦 임베딩 및 인덱스 완료 → {DATA_DIR}/faiss_books.index")
    return index

# -------------------------
# 실행
# -------------------------
if __name__ == "__main__":
    new_books = collect_books_incremental()           # 이번 실행에서 새로 수집된 도서만 반환
    all_desc = match_google_books(new_books)          # 새로 들어온 도서만 Google Books 매칭 후 누적 갱신
    build_faiss_index(all_desc)                       # 설명 있는 전체 데이터로 인덱스 재생성
