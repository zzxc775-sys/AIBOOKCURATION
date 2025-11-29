from full_incremental_pipeline import fetch_google_book_info
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. 2600페이지까지 수집한 ISBN 데이터 로드
all_books = pd.read_csv("data/books_partial_2600.csv")

# 2. Google Books API로 description 빠르게 수집
def fetch_info(isbn):
    return fetch_google_book_info(isbn)

matched_books = []
target_isbns = all_books["isbn"].dropna().unique()  # 중복, NaN 제거

print(f"▶ Google Books 설명 수집 (멀티스레드): 총 {len(target_isbns)}권")

# 3. 병렬 요청 (15개 스레드)
with ThreadPoolExecutor(max_workers=15) as executor:
    futures = {executor.submit(fetch_info, isbn): isbn for isbn in target_isbns}
    for i, future in enumerate(as_completed(futures), start=1):
        result = future.result()
        if result and result["description"]:
            matched_books.append(result)
            print(f"✅ [{i}/{len(target_isbns)}] {result['title']}")
        else:
            print(f"⚠️ [{i}/{len(target_isbns)}] 설명 없음")

# 4. 결과 CSV 저장 (나중에 sort.py로 합치기 가능)
pd.DataFrame(matched_books).to_csv(
    "data/books_with_descriptions_resume.csv",
    index=False,
    encoding="utf-8-sig"
)
print(f"📁 {len(matched_books)}권 description 수집 완료 (books_partial_2600 기준)")
