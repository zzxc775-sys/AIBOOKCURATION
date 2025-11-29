from full_incremental_pipeline import fetch_google_book_info
import pandas as pd, time

all_books = pd.read_csv("data/books_partial_2600.csv")
books_to_process = all_books  # 전체 처리

matched_books = []

for i, isbn in enumerate(books_to_process["isbn"], start=1):
    book = fetch_google_book_info(isbn)
    if book and book["description"]:
        matched_books.append(book)
        print(f"✅ [{i}/{len(all_books)}] 설명 수집: {book['title']}")
    else:
        print(f"⚠️ [{i}/{len(all_books)}] 설명 없음")
    time.sleep(0.4)

pd.DataFrame(matched_books).to_csv(
    "data/books_with_descriptions_resume.csv",
    index=False,
    encoding="utf-8-sig"
)
print(f"📁 {len(matched_books)}권 description 수집 완료")
