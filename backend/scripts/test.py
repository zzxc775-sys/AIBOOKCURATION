import requests
import time

API_KEY = "acb95e5a2989c1fe3507d7119fb16cf35f331355485bf12f2683eb153ccc1f5e"
headers = {"User-Agent": "Mozilla/5.0"}

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

def check_pages(start=5701, end=5750, sleep_sec=1.2):
    empty_count = 0
    for page in range(start, end + 1):
        print(f"\n🔍 page {page} 확인 중...")
        result = fetch_page(page)
        if result and result.get("docs"):
            count = len(result["docs"])
            print(f"✅ 도서 {count}권 존재")
            empty_count = 0  # 리셋
        else:
            print("📭 비어있음")
            empty_count += 1
        time.sleep(sleep_sec)

        # 5페이지 연속 비어있으면 중단
        if empty_count >= 5:
            print("\n⚠️ 5페이지 연속 결과 없음 → API 끝일 가능성 매우 높음!")
            break

    print("\n✅ 검사 완료")

if __name__ == "__main__":
    check_pages(start=5701, end=5750)
