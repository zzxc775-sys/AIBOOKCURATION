import requests

BASE="http://127.0.0.1:8000"

# 1) recommend로 책 먼저 가져오기
r = requests.post(f"{BASE}/recommend", json={"query":"일에 몰입하는 법 책 추천", "top_k":5}, timeout=120)
r.raise_for_status()
j = r.json()
books = j["results"][:3]

# 2) summary 호출 payload 만들기
top3 = []
for idx, b in enumerate(books, 1):
    text = (b.get("description") or b.get("content") or "").strip()
    text = " ".join(text.split())
    if len(text) > 80:
        text = text[:80] + "..."
    top3.append({
        "title": b.get("title"),
        "author": b.get("author"),
        "snippet": text,
        "rank": idx
    })

s = requests.post(f"{BASE}/summary", json={"query":"일에 몰입하는 법 책 추천", "books": top3}, timeout=120)
s.raise_for_status()
print(s.json())
