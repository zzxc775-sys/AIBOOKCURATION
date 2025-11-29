import argparse
import re
import time
from core.retriever import BookRetriever
from core.llm_intergration import DeepSeekRecommender

def clean_query(query: str) -> str:
    """사용자 입력 정제: 특수문자 제거 및 공백 처리"""
    return re.sub(r'[^\w\s가-힣]', '', query).strip()

def get_user_input():
    """사용자로부터 검색어 입력 받기"""
    print("\n" + "="*50)
    print("📚 도서 추천 시스템에 오신 것을 환영합니다!")
    print("="*50)
    print("※ 추천 도서는 항상 5권으로 고정됩니다")
    print("="*50)
    
    while True:
        query = input("\n어떤 책을 찾고 계신가요? (예: 자기계발, 시간 여행 소설)\n> ")
        cleaned_query = clean_query(query)
        
        if cleaned_query:
            return cleaned_query
        print("⚠️ 유효한 검색어를 입력해주세요.")

def print_basic_recommendation(query, results):
    """AI 추천 실패 시 기본 추천 출력"""
    print(f"\n🔍 '{query}' 관련 추천 도서 (5권):")
    for i, book in enumerate(results, 1):
        print(f"\n{i}. [{book.get('id', 'N/A')}] {book['title']}")
        print(f"   👤 저자: {book['author']}")
        content_preview = book['description'][:100] + "..." if len(book['description']) > 100 else book['description']
        print(f"   📖 내용: {content_preview}")
        print(f"   ⭐ 유사도: {book.get('score', 0):.2f}")

def main():
    # 인덱스 경로를 단일 파일로 변경
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=str, default="data/faiss_books.index",
                       help="FAISS 인덱스 파일 경로")
    args = parser.parse_args()
    
    retriever = BookRetriever(args.index)
    
    # DeepSeek 사용 비활성화
    use_deepseek = False
    """
    try:
        recommender = DeepSeekRecommender()
        use_deepseek = True
        print("✅ DeepSeek API 연결 성공")
    except ValueError as e:
        print(f"⚠️ {str(e)}")
        use_deepseek = False
        print("ℹ️ 기본 도서 목록 형식으로 출력됩니다")
    """
    while True:
        query = get_user_input()
        start_time = time.time()
        results = retriever.retrieve(query, top_k=5)
        search_time = time.time() - start_time
        
        if not results:
            print("\n😢 해당 주제에 맞는 도서를 찾지 못했습니다.")
        else:
            print(f"\n검색 소요 시간: {search_time:.2f}s")
            print_basic_recommendation(query, results)

         # --- 여기서 계속할지 묻기 ---
        while True:
            cont = input("\n계속 검색하시겠습니까? (y/n): ").strip().lower()
            if cont == "y":
                break  # 다시 검색 시작
            elif cont == "n":
                print("\n프로그램을 종료합니다. 이용해주셔서 감사합니다!")
                return
            else:
                print("⚠️ y 또는 n으로 입력해주세요.")

        if use_deepseek:
            try:
                api_start = time.time()
                recommendation = recommender.generate_recommendation(query, results)
                api_time = time.time() - api_start
                
                print(f"\n⏱️ 검색 시간: {search_time:.2f}s | API 처리 시간: {api_time:.2f}s")
                print(f"🪙 토큰 사용량: {recommendation['usage']}")
                
                print("\n" + "="*50)
                print("📚 AI 도서 추천:")
                print("="*50)
                print(recommendation['content'])
                print("="*50)
            except Exception as e:
                print(f"\n⚠️ AI 추천 생성 오류: {str(e)}")
                print_basic_recommendation(query, results)
        else:
            print_basic_recommendation(query, results)

if __name__ == "__main__":
    main()
