import pandas as pd
import re
import json
import uuid
import argparse
import os
from typing import Dict, List
from pathlib import Path

def preprocess_data():
    # 경로 설정
    BASE_DIR = Path(__file__).resolve().parent.parent
    RAW_PATH = os.path.join(BASE_DIR, 'data', 'busan_example_data.csv')
    SAVE_PATH = os.path.join(BASE_DIR, 'data', 'preprocessed_books.csv')
    
    # 데이터 로드
    try:
        df = pd.read_csv(RAW_PATH, encoding='cp949', skiprows=2)
    except UnicodeDecodeError:
        df = pd.read_csv(RAW_PATH, encoding='euc-kr', skiprows=2)
    
    # 열 이름 정리
    df.columns = df.columns.str.strip()
    
    def clean_isbn(isbn_str):
        if pd.isna(isbn_str):
            return None
        isbn = str(isbn_str).upper().replace('E+', '')
        isbn = ''.join(filter(str.isdigit, isbn))
        return isbn.zfill(13)[:13] if isbn else None
    
    # ISBN 컬럼이 있을 경우에만 처리
    if '국제표준도서번호(ISBN)' in df.columns:
        df['국제표준도서번호(ISBN)'] = df['국제표준도서번호(ISBN)'].apply(clean_isbn)

    # 결과 저장
    os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
    df.to_csv(SAVE_PATH, index=False, encoding='utf-8-sig')
    print(f"전처리 완료! 저장 위치: {SAVE_PATH}")
    print(f"처리된 레코드 수: {len(df)}건")

if __name__ == "__main__":
    preprocess_data()

class BookDataPreprocessor:
    def __init__(self):
        self.required_columns = [
            'title', 'author', 'summery', 'readers'
        ]
    
    def _extract_publisher(self, author_str: str) -> Dict:
        """저자 문자열에서 출판사 정보 분리"""
        if '(' in author_str and ')' in author_str:
            name_part = author_str.split('(')[0].strip()
            publisher = re.search(r'\((.*?)\)', author_str).group(1)
            return {"author": name_part, "publisher": publisher}
        return {"author": author_str, "publisher": ""}
    
    def _process_tags(self, tag_str: str) -> List[str]:
        """해시태그 문자열을 리스트로 변환"""
        return [tag.strip() for tag in tag_str.split(',')] if tag_str else []
    
    def process(self, input_path: str, save_path: str):
        """수정된 process 메서드 - 중복 제거 로직 추가"""
         # 1. 저장 디렉토리 생성
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
        # 2. CSV 파일 로드
        try:
            df = pd.read_csv(input_path, encoding='utf-8-sig')
        except UnicodeDecodeError:
            df = pd.read_csv(input_path, encoding='cp949')
    
        # 3. 컬럼 검증
        missing_cols = [col for col in self.required_columns if col not in df.columns]
        if missing_cols:
            raise ValueError(f"필수 컬럼 누락: {', '.join(missing_cols)}")
    
        # 4. 원본 데이터 저장 (JSON)
        raw_books = []
        for _, row in df.iterrows():
            raw_books.append({
                "title": row['title'],
                "author_info": self._extract_publisher(row['author']),
                "summary": row['summery'],
                "target_readers": row['readers']
            })
    
        raw_books_path = os.path.join(os.path.dirname(save_path), "raw_books.json")
        with open(raw_books_path, 'w', encoding='utf-8') as f:
            json.dump(raw_books, f, ensure_ascii=False, indent=2)
    
        # 5. 전처리된 데이터 저장 (CSV) - 중복 제거 추가
        processed_data = []
        seen_identifiers = set()  # 중복 체크를 위한 집합
    
        for book in raw_books:
            # 저자 이름 정제 (첫 번째 저자만 사용)
            author_name = book['author_info']['author']
            if ';' in author_name:
                author_name = author_name.split(';')[0]
            if ',' in author_name:
                author_name = author_name.split(',')[0]
            author_name = author_name.strip()
        
            # 고유 식별자 생성 (제목 + 저자)
            title_clean = re.sub(r'\s+', ' ', book['title']).strip()  # 연속 공백 제거
            identifier = f"{title_clean}_{author_name}"
        
            # 중복 확인
            if identifier in seen_identifiers:
                continue  # 중복이면 건너뜀
            
            seen_identifiers.add(identifier)
        
            processed_data.append({
                "id": str(uuid.uuid4()),
                "title": title_clean,
                "author": author_name,
                "publisher": book['author_info']['publisher'],
                "description": book['summary'],
                "target_audience": book['target_readers']
            })
    
        processed_df = pd.DataFrame(processed_data)
        processed_df.to_csv(save_path, index=False, encoding='utf-8-sig')
    
        # 중복 제거 통계 출력
        original_count = len(raw_books)
        processed_count = len(processed_data)
        duplicates_removed = original_count - processed_count
        print(f"중복 제거: {duplicates_removed}건 제거됨 ({original_count} → {processed_count})")
    
        return processed_df

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='도서 데이터 전처리 스크립트')
    parser.add_argument('--input', type=str, required=True, help='입력 CSV 파일 경로')
    parser.add_argument('--output', type=str, default='data/processed_books.csv', help='처리된 데이터 저장 경로')
    args = parser.parse_args()
    
    preprocessor = BookDataPreprocessor()
    processed_df = preprocessor.process(args.input, args.output)
    print(f"✅ 전처리 완료: {len(processed_df)}권의 도서 데이터 저장됨 ({args.output})")

