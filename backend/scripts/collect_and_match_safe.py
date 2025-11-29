import os, re, time, requests, asyncio, aiohttp, pandas as pd
from typing import List

# =========================
# 설정
# =========================
API_KEY = "acb95e5a2989c1fe3507d7119fb16cf35f331355485bf12f2683eb153ccc1f5e"
headers = {"User-Agent": "Mozilla/5.0"}
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# 기존 CSV의 ISBN까지 정규화해 재저장할지 여부
NORMALIZE_EXISTING = True

# Google Books 호출 동시성(너무 크면 429 위험)
MAX_CONCURRENCY = 5

# =========================
# ISBN 정규화 & 검증
# =========================
ISBN_CANDIDATE_RE = re.compile(r'(\d{13}|\d{9}[\dXx])')

def _clean_isbn_chars(s: str) -> str:
    if not s:
        return ""
    # 하이픈/슬래시/파이프 등 구분자는 공백으로 치환 후 토큰화
    s = s.replace("-", " ").replace("|", " ").replace("/", " ")
    return s

def _isbn10_to_13(isbn10: str) -> str:
    """필요 시 ISBN-10을 ISBN-13으로 변환(접두 978)"""
    core = "978" + isbn10[:-1]
    total = 0
    for i, ch in enumerate(core):
        d = int(ch)
        total += d if i % 2 == 0 else 3 * d
    check = (10 - (total % 10)) % 10
    return core + str(check)

def is_valid_isbn13(s: str) -> bool:
    if not s or len(s) != 13 or not s.isdigit():
        return False
    total = 0
    for i, ch in enumerate(s):
        d = int(ch)
        total += d if i % 2 == 0 else 3 * d
    return total % 10 == 0

def is_valid_isbn10(s: str) -> bool:
    if not s or len(s) != 10:
        return False
    total = 0
    for i, ch in enumerate(s[:9]):
        if not ch.isdigit():
            return False
        total += (10 - i) * int(ch)
    check = s[9].upper()
    total += 10 if check == "X" else (0 if not check.isdigit() else int(check))
    return total % 11 == 0

def normalize_isbn(raw: str) -> str:
    """여러 개 섞인 EA_ISBN에서 13자리 우선, 없으면 10자리 중 유효한 것을 선택하여 13자리로 통일"""
    if not raw:
        return ""
    raw = _clean_isbn_chars(str(raw))
    cands = [c.upper() for c in ISBN_CANDIDATE_RE.findall(raw)]
    # 13자리 중 유효한 것 우선
    for c in cands:
        if len(c) == 13 and is_valid_isbn13(c):
            return c
    # 10자리 중 유효한 것 → 13자리로 변환
    for c in cands:
        if len(c) == 10 and is_valid_isbn10(c):
            return _isbn10_to_13(c)
    # 그래도 못 찾으면 숫자만 추린 13자리 후보(검증 없이) 마지막 시도
    for c in cands:
        if len(c) == 13 and c.isdigit():
            return c
    return ""

# =========================
# 시리즈물 판단 및 정리(제목 중복 방지용)
# =========================
def is_series_volume(title):
    if not isinstance(title, str):
        return False
    title = title.lower()
    patterns = [
        r"\b\d+\s*권\b", r"제\s*\d+\s*권", r"\bvol\.?\s*\d+",
        r"\bvolume\s*\d+", r"\bbook\s*\d+", r"\bpart\s*\d+",
        r"시즌\s*\d+", r"[\[\(]?\d+\s*권[\]\)]?", r"\s\d{1,2}$", r"[^\d]\d{1,2}$"
    ]
    return any(re.search(p, title) for p in patterns)

def clean_title_prefix(title):
    if not isinstance(title, str):
        title = ""
    title = re.sub(r"[\s\(\[].*?\d+.*?[\)\]]", "", title)
    title = re.sub(r"제\s*\d+\s*권", "", title)
    title = re.sub(r"\b\d+\s*권\b", "", title)
    title = re.sub(r"vol\.?\s*\d+", "", title, flags=re.I)
    title = re.sub(r"volume\s*\d+", "", title, flags=re.I)
    title = re.sub(r"book\s*\d+", "", title, flags=re.I)
    title = re.sub(r"\s\d{1,2}$", "", title)
    title = re.sub(r"\d{1,2}$", "", title)
    return title.strip()

# =========================
# 국립중앙도서관 API
# =========================
def fetch_page(page_no):
    params = {
        "cert_key": API_KEY,
        "result_style": "json",
        "page_no": page_no,
        "page_size": 100,
        "sort": "INPUT_DATE",
        "order_by": "DESC"
    }
    try:
        res = requests.get("https://www.nl.go.kr/seoji/SearchApi.do", params=params, headers=headers, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"❌ 오류 (page {page_no}): {e}")
        return None

# =========================
# 수집(동기) - ISBN 정규화 적용
# =========================
def collect_books_sync():
    collected_file = f"{DATA_DIR}/books_collected.csv"
    if os.path.exists(collected_file):
        existing_df = pd.read_csv(collected_file)
    else:
        existing_df = pd.DataFrame(columns=["title", "author", "isbn"])

    # (옵션) 기존 CSV의 ISBN도 정규화해 통일
    if NORMALIZE_EXISTING and not existing_df.empty:
        existing_df["isbn"] = existing_df["isbn"].astype(str).fillna("").apply(normalize_isbn)
        existing_df = existing_df[existing_df["isbn"] != ""]

    existing_df["title"] = existing_df["title"].fillna("")
    collected_isbns = set(existing_df["isbn"])
    title_prefix_set = set(existing_df["title"].apply(clean_title_prefix)) if not existing_df.empty else set()

    # 이어받기
    last_page_file = f"{DATA_DIR}/last_page.txt"
    last_page = int(open(last_page_file).read()) if os.path.exists(last_page_file) else 0
    start_page = last_page + 1
    end_page = start_page + 999

    print(f"\n📘 국립중앙도서관 수집 시작: {start_page} ~ {end_page} 페이지 (동기 방식)")
    new_books = []

    for page_no in range(start_page, end_page + 1):
        data = fetch_page(page_no)
        if not data or "docs" not in data:
            continue

        for item in data["docs"]:
            raw_title = str(item.get("TITLE", "")).strip()
            raw_isbn = str(item.get("EA_ISBN", "")).strip()
            author = str(item.get("AUTHOR", "")).strip()

            isbn = normalize_isbn(raw_isbn)
            if not isbn or not raw_title or isbn in collected_isbns:
                continue

            if is_series_volume(raw_title):
                prefix = clean_title_prefix(raw_title)
                if prefix in title_prefix_set:
                    continue
                title_prefix_set.add(prefix)
            else:
                prefix = raw_title.strip()
                if prefix in title_prefix_set:
                    continue
                title_prefix_set.add(prefix)

            new_books.append({"title": raw_title, "author": author, "isbn": isbn})
            collected_isbns.add(isbn)

        if page_no % 50 == 0:
            print(f"📥 {page_no} 페이지 완료 - 누적 수집 {len(new_books)}권")
        time.sleep(1.2)

    # 저장(정규화된 ISBN 기준으로 중복 제거)
    final_df = pd.concat([existing_df, pd.DataFrame(new_books)], ignore_index=True)
    final_df = final_df.drop_duplicates(subset=["isbn"])
    final_df.to_csv(collected_file, index=False, encoding="utf-8-sig")

    with open(last_page_file, "w") as f:
        f.write(str(end_page))

    print(f"\n📁 누적 도서 데이터: 총 {len(final_df)}권 (신규 {len(new_books)}권)")
    return pd.DataFrame(new_books)

# =========================
# Google Books API 설명 수집 (비동기 + 지수 백오프)
# =========================
async def fetch_google_description(session, isbn: str, retries=3):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    backoff = 0.5
    for attempt in range(1, retries + 1):
        try:
            await asyncio.sleep(backoff)  # 0.5 → 1.0 → 2.0 ...
            async with session.get(url, timeout=15) as res:
                if res.status == 429:
                    # Too Many Requests → 백오프 후 재시도
                    raise aiohttp.ClientResponseError(res.request_info, res.history, status=429, message="Too Many Requests")
                res.raise_for_status()
                data = await res.json()
                if "items" not in data or not data["items"]:
                    raise ValueError("No items in response")
                info = data["items"][0].get("volumeInfo", {})
                description = (info.get("description") or "").strip()
                if not description:
                    raise ValueError("No description found")
                return {
                    "title": (info.get("title") or "").strip(),
                    "author": ", ".join(info.get("authors", [])) if info.get("authors") else "",
                    "isbn": isbn,  # 정규화된 값
                    "description": description
                }
        except Exception as e:
            print(f"⚠️ [{isbn}] 시도 {attempt} 실패: {e}")
            backoff *= 2
    return None

async def match_google_books(isbn_list: List[str]):
    desc_file = f"{DATA_DIR}/books_with_descriptions.csv"
    if os.path.exists(desc_file):
        existing_df = pd.read_csv(desc_file)
    else:
        existing_df = pd.DataFrame(columns=["title", "author", "isbn", "description"])

    # (옵션) 기존 설명 CSV도 정규화해 통일
    if NORMALIZE_EXISTING and not existing_df.empty:
        existing_df["isbn"] = existing_df["isbn"].astype(str).fillna("").apply(normalize_isbn)
        existing_df = existing_df[existing_df["isbn"] != ""]

    # 타깃도 정규화
    norm_targets = []
    for x in isbn_list:
        nx = normalize_isbn(x)
        if nx:
            norm_targets.append(nx)

    existing_isbns = set(existing_df["isbn"])
    targets = [t for t in norm_targets if t not in existing_isbns]
    print(f"\n📗 Google 설명 수집 대상: {len(targets)}권")

    matched_books = []
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def worker(isbn):
        async with sem:
            book = await fetch_google_description(session, isbn)
            if book:
                matched_books.append(book)
                print(f"✅ {book['title']} ({isbn})")
            else:
                print(f"❌ {isbn} 최종 실패")

    async with aiohttp.ClientSession() as session:
        # 순차 대신 태스크 병렬
        tasks = [asyncio.create_task(worker(isbn)) for isbn in targets]
        await asyncio.gather(*tasks)

    updated_df = pd.concat([existing_df, pd.DataFrame(matched_books)], ignore_index=True)
    updated_df = updated_df.drop_duplicates(subset=["isbn"])
    updated_df.to_csv(desc_file, index=False, encoding="utf-8-sig")

    # 실패 목록 파일
    failures = [t for t in targets if t not in set(updated_df["isbn"])]
    if failures:
        fail_file = f"{DATA_DIR}/failed_google_books.txt"
        with open(fail_file, "w") as f:
            f.write("\n".join(failures))
        print(f"⚠️ 실패한 ISBN {len(failures)}권 → {fail_file} 저장됨")

    print(f"\n📁 설명 포함 도서 총: {len(updated_df)}권")
    return updated_df

# =========================
# 실행부
# =========================
if __name__ == "__main__":
    new_books = collect_books_sync()
    if not new_books.empty:
        asyncio.run(match_google_books(new_books["isbn"].tolist()))
    else:
        print("🛑 신규 도서 없음, 설명 수집 생략")
