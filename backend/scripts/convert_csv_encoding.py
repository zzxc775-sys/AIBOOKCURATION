import pandas as pd
import os

# 변환할 파일 경로
file_path = "data/books_with_descriptions.csv"

# 백업 파일 생성 (원본 보관용)
backup_path = file_path.replace(".csv", "_backup.csv")
if not os.path.exists(backup_path):
    os.rename(file_path, backup_path)
    print(f"원본 백업 완료: {backup_path}")
else:
    print(f"기존 백업 파일이 있어 원본은 건드리지 않음: {backup_path}")

# CP949로 읽고 UTF-8-SIG로 다시 저장
try:
    df = pd.read_csv(backup_path, encoding="cp949", low_memory=False)
    df.to_csv(file_path, index=False, encoding="utf-8-sig")
    print(f"CSV 인코딩 변환 완료 → {file_path} (UTF-8-SIG)")
except Exception as e:
    print(f"❌ 변환 실패: {e}")
