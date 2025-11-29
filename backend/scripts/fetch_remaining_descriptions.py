from full_incremental_pipeline import fetch_google_book_info
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import os, time

DATA_DIR = "data"

collected_file = os.path.join(DATA_DIR, "books_collected.csv")
desc_file = os.path.join(DATA_DIR, "books_with_descriptions.csv")

all_books = pd.read_csv(collected_file)
existing_desc = pd.read_csv(desc_file)

# 18만 권 이후 데이터만 선택 (2601페이지 기준, 18만 권쯤)
target_books = all_books.iloc[180000:].copy()

# 이미 description 있는 ISBN 제외
desc_isbns = set(existing_desc["isbn"])
target_books = target_books[~target_books["isbn"].isin(desc_isbns)]
target_isbns = target_books["isbn"].dropna().unique()

print(f"▶ Google Books description 수집 (18만 권 이후): 대상 {len(target_isbns)}권")

matched_books = []
failed_isbns = []

def fetch_with_retry(isbn, retries=3):
    for attempt in range(1, retries + 1):
        try:
            result = fetch_google_book_info(isbn)
            if result and result["description"]:
                return result
        except Exception as e:
            print(f"⚠️ {isbn} 시도 {attempt} 실패: {e}")
        time.sleep(1)
    failed_isbns.append(isbn)
    return None

chunk_size = 1000
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(fetch_with_retry, isbn): isbn for isbn in target_isbns}
    for i, future in enumerate(as_completed(futures), start=1):
        result = future.result()
        if result:
            matched_books.append(result)
            print(f"✅ [{i}/{len(target_isbns)}] {result['title']}")
        else:
            print(f"❌ [{i}/{len(target_isbns)}] 실패 또는 설명 없음")

        if i % chunk_size == 0:
            temp_file = os.path.join(DATA_DIR, f"descriptions_partial_{i}.csv")
            pd.DataFrame(matched_books).to_csv(temp_file, index=False, encoding="utf-8-sig")
            print(f"💾 중간 저장: {temp_file}")

# 최종 병합
new_desc_df = pd.DataFrame(matched_books)
final_desc_df = pd.concat([existing_desc, new_desc_df]).drop_duplicates(subset=["isbn"])

final_file = os.path.join(DATA_DIR, "books_with_descriptions.csv")
final_desc_df.to_csv(final_file, index=False, encoding="utf-8-sig")

print(f"📁 최종 description 데이터 저장 완료: {len(final_desc_df)}권 → {final_file}")

if failed_isbns:
    log_file = os.path.join(DATA_DIR, "failed_isbns.txt")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("\n".join(failed_isbns))
    print(f"⚠️ 실패한 ISBN {len(failed_isbns)}개 → {log_file}")
