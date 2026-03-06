import argparse
import re
import time
from core.retriever import BookRetriever


def clean_query(query: str) -> str:
    """사용자 입력 정제: 특수문자 제거 및 공백 처리"""
    return re.sub(r"[^\w\s가-힣]", "", query).strip()


def get_user_input() -> str:
    """사용자로부터 검색어 입력 받기"""
    print("\n" + "=" * 50)
    print("📚 도서 추천 시스템에 오신 것을 환영합니다!")
    print("=" * 50)
    print("※ 추천 도서는 항상 5권으로 고정됩니다")
    print("=" * 50)

    while True:
        query = input("\n어떤 책을 찾고 계신가요? (예: 자기계발, 시간 여행 소설)\n> ")
        cleaned_query = clean_query(query)

        if cleaned_query:
            return cleaned_query
        print("⚠️ 유효한 검색어를 입력해주세요.")


def print_basic_recommendation(query: str, results: list) -> None:
    """기본 추천 출력"""
    print(f"\n🔍 '{query}' 관련 추천 도서 (5권):")

    for i, book in enumerate(results, 1):
        title = book.get("title", "제목 없음")
        author = book.get("author") or "저자 정보 없음"
        description = (book.get("description") or book.get("content") or "").strip()
        score = book.get("score", 0)

        if description:
            content_preview = description[:100] + "..." if len(description) > 100 else description
        else:
            content_preview = "설명 없음"

        print(f"\n{i}. [{book.get('id', 'N/A')}] {title}")
        print(f"   👤 저자: {author}")
        print(f"   📖 내용: {content_preview}")
        print(f"   ⭐ 유사도: {score:.2f}")


def ask_continue() -> bool:
    """계속 검색 여부 확인"""
    while True:
        cont = input("\n계속 검색하시겠습니까? (y/n): ").strip().lower()
        if cont == "y":
            return True
        if cont == "n":
            print("\n프로그램을 종료합니다. 이용해주셔서 감사합니다!")
            return False
        print("⚠️ y 또는 n으로 입력해주세요.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--index",
        type=str,
        default="data/faiss_books.index",
        help="FAISS 인덱스 파일 경로",
    )
    args = parser.parse_args()

    try:
        retriever = BookRetriever(args.index)
    except Exception as e:
        print(f"❌ BookRetriever 초기화 실패: {e}")
        return

    while True:
        query = get_user_input()

        try:
            start_time = time.time()
            results = retriever.retrieve(query, top_k=5)
            search_time = time.time() - start_time
        except Exception as e:
            print(f"\n❌ 검색 중 오류가 발생했습니다: {e}")
            if ask_continue():
                continue
            return

        if not results:
            print("\n😢 해당 주제에 맞는 도서를 찾지 못했습니다.")
        else:
            print(f"\n⏱️ 검색 소요 시간: {search_time:.2f}s")
            print_basic_recommendation(query, results)

        if not ask_continue():
            return


if __name__ == "__main__":
    main()
