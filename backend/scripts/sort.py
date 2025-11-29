import pandas as pd

existing = pd.read_csv("data/books_with_descriptions.csv")
new_part = pd.read_csv("data/books_with_descriptions_resume.csv")

# 합치고 중복 ISBN 제거
merged = pd.concat([existing, new_part]).drop_duplicates(subset=["isbn"])

# 최종 파일로 저장
merged.to_csv("data/books_with_descriptions.csv", index=False, encoding="utf-8-sig")
print(f"최종 {len(merged)}권 description 데이터 병합 완료")
