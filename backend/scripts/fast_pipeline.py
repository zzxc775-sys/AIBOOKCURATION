import os, re, time, asyncio, aiohttp
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss
import requests

API_KEY = "acb95e5a2989c1fe3507d7119fb16cf35f331355485bf12f2683eb153ccc1f5e"
headers = {"User-Agent": "Mozilla/5.0"}
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------- 공통 유틸 ----------------
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

# ---------------- 국립중앙도서관 수집 (세마포어로 동시 10개 제한) ----------------
async def fetch_page(session, page_no, sem, retries=3):
    params = {
        "cert_key": API_KEY, "result_style": "json",
        "page_no": page_no, "page_size": 100,
        "sort": "INPUT_DATE", "order_by": "DESC"
    }
    for attempt in range(1, retries+1):
        try:
            async with sem:  # 동시 요청 제한
                async with session.get("https://www.nl.go.kr/seoji/SearchApi.do", params=params, headers=headers, timeout=30) as res:
                    res.raise_for_status()
                    return await res.json()
        except Exception as e:
            print(f"❌ 오류 (page {page_no}, 시도 {attempt}): {e}")
            await asyncio.sleep(3)
    return None

async def collect_books_async(start_page, end_page):
    collected_file = f"{DATA_DIR}/books_collected.csv"
    existing_df = pd.read_csv(collected_file) if os.path.exists(collected_file) else pd.DataFrame(columns=["title","author","isbn"])
    collected_isbns = set(existing_df["isbn"])
    title_prefix_set = set(existing_df["title"].apply(clean_title_prefix)) if not existing_df.empty else set()

    print(f"▶ 국립중앙도서관 데이터 수집: {start_page} ~ {end_page} 페이지 (동시 10개 제한)")

    new_books = []
    sem = asyncio.Semaphore(10)  # 동시 요청 10개로 제한
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_page(session, p, sem) for p in range(start_page, end_page+1)]
        results = await asyncio.gather(*tasks)

    for data in results:
        if not data:
            continue
        print(f"📄 page 응답: {len(data.get('docs', []))}권")

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

    final_df = pd.concat([existing_df, pd.DataFrame(new_books)]).drop_duplicates(subset=["isbn"])
    final_df.to_csv(collected_file, index=False, encoding="utf-8-sig")
    print(f"📁 누적 도서 데이터: {len(final_df)}권 (신규 {len(new_books)}권)")

    # 블록별 중간 저장
    block_file = f"{DATA_DIR}/books_partial_{end_page}.csv"
    pd.DataFrame(new_books).to_csv(block_file, index=False, encoding="utf-8-sig")
    print(f"💾 중간 저장: {block_file}")

    return pd.DataFrame(new_books)

def collect_books_safe():
    last_page_file = f"{DATA_DIR}/last_page.txt"
    if os.path.exists(last_page_file):
        with open(last_page_file, "r") as f:
            last_page = int(f.read().strip())
    else:
        last_page = 4600  # 없으면 4600에서 시작
    start_page = last_page + 1
    end_page = start_page + 99

    new_books = asyncio.run(collect_books_async(start_page, end_page))

    # 다음 실행을 위한 last_page 갱신
    with open(last_page_file, "w") as f:
        f.write(str(end_page))

    return new_books

# ---------------- Google Books API (재시도 + 부분 저장) ----------------
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

def match_google_books_safe(new_books_df, max_workers=10, chunk_size=1000):
    desc_file = f"{DATA_DIR}/books_with_descriptions.csv"
    existing_desc = pd.read_csv(desc_file) if os.path.exists(desc_file) else pd.DataFrame(columns=["title","author","isbn","description"])
    existing_isbns = set(existing_desc["isbn"])

    target_isbns = [isbn for isbn in new_books_df["isbn"] if isbn not in existing_isbns]
    print(f"▶ Google Books 매칭: 대상 {len(target_isbns)}권")

    matched_books, failed_isbns = [], []

    def fetch_with_retry(isbn, retries=3):
        for attempt in range(1, retries+1):
            result = fetch_google_book_info(isbn)
            if result and result["description"]:
                return result
            time.sleep(1)
        failed_isbns.append(isbn)
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_with_retry, isbn): isbn for isbn in target_isbns}
        for i, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            if result:
                matched_books.append(result)
                print(f"✅ [{i}/{len(target_isbns)}] {result['title']}")
            else:
                print(f"❌ [{i}/{len(target_isbns)}] 실패 또는 설명 없음")

            if i % chunk_size == 0:
                temp_file = f"{DATA_DIR}/descriptions_partial_{i}.csv"
                pd.DataFrame(matched_books).to_csv(temp_file, index=False, encoding="utf-8-sig")
                print(f"💾 중간 저장: {temp_file}")

    # 최종 병합
    new_desc_df = pd.DataFrame(matched_books)
    all_desc_df = pd.concat([existing_desc, new_desc_df]).drop_duplicates(subset=["isbn"])
    all_desc_df.to_csv(desc_file, index=False, encoding="utf-8-sig")

    if failed_isbns:
        log_file = f"{DATA_DIR}/failed_isbns_partial_{len(failed_isbns)}.txt"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("\n".join(failed_isbns))
        print(f"⚠️ 실패 ISBN {len(failed_isbns)}개 기록: {log_file}")

    print(f"📁 설명 데이터 갱신: 총 {len(all_desc_df)}권")
    return all_desc_df

# ---------------- FAISS 점진적 업데이트 ----------------
"""
def update_faiss_index(df_new_desc):
    model = SentenceTransformer("jhgan/ko-sroberta-multitask")
    df_new_desc = df_new_desc.fillna("")
    texts = (df_new_desc["title"] + " " + df_new_desc["author"] + " " + df_new_desc["description"]).astype(str).tolist()
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)

    index_file = f"{DATA_DIR}/faiss_books.index"
    if os.path.exists(index_file):
        index = faiss.read_index(index_file)
        index.add(embeddings)
    else:
        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings)

    faiss.write_index(index, index_file)
    print(f"📦 FAISS 인덱스 갱신 완료 → {index_file}")
"""
# ---------------- 실행 ----------------
if __name__ == "__main__":
    new_books = collect_books_safe()                     # 4601페이지(37만 이후) 수집
    new_desc = match_google_books_safe(new_books)        # description 수집 (안전 모드)
    #update_faiss_index(new_desc)                         # 신규 데이터만 인덱스에 추가 (원하면 주석 처리)
