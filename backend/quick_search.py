# quick_search.py
# 사용법 예)
#   python quick_search.py --q "연인과 헤어져 슬픈 친구에게 위로가 되는 책" -k 5 --mode stars
#   python quick_search.py                         # 인터랙티브 모드로 질문 반복
# 점수 모드:
#   stars(기본) | score_pct | rel_pct | none | raw

from __future__ import annotations
import argparse
import sys
import os
from typing import List, Dict

# Windows 콘솔에서 한글 깨짐 방지 (가능한 경우만)
try:
    import locale
    if sys.platform.startswith("win"):
        sys.stdout.reconfigure(encoding=locale.getpreferredencoding(False))
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def parse_args():
    p = argparse.ArgumentParser(description="AI Book Quick Search")
    p.add_argument("--q", "--query", dest="query", type=str, default=None, help="검색 질의")
    p.add_argument("-k", "--top-k", dest="top_k", type=int, default=5, help="상위 N개 결과 (기본 5)")
    p.add_argument("--mode", dest="mode", type=str, default="score_pct",
                   choices=["stars", "score_pct", "rel_pct", "none", "raw"],
                   help="점수 표기 모드 (기본: stars)")
    p.add_argument("--index-dir", dest="index_dir", type=str, default="models/faiss_index",
                   help="FAISS 인덱스 폴더 경로 (기본: models/faiss_index)")
    return p.parse_args()

def fmt_score(b: Dict, mode: str) -> str:
    if mode == "none":
        return ""
    if mode == "stars":
        val = b.get("stars")
        return f" | ★ {val:.1f}/5.0 (유사도)" if isinstance(val, (int, float)) else ""
    if mode == "score_pct":
        val = b.get("score_pct")
        return f" | 유사도 {int(val)}%" if isinstance(val, (int, float)) else ""
    if mode == "rel_pct":
        val = b.get("rel_pct")
        return f" | 이 검색에서 {int(val)}%" if isinstance(val, (int, float)) else ""
    if mode == "raw":
        # 코사인, %, 상대%, 별점, 거리 모두 보여주기
        return (" | score={:.3f}, score_pct={}%, rel_pct={}%, stars={:.1f}, dist={}"
                .format(b.get("score", 0.0),
                        int(b.get("score_pct", 0)),
                        int(b.get("rel_pct", 0)),
                        float(b.get("stars", 0.0)),
                        "NA" if b.get("distance") is None else f"{float(b['distance']):.4f}"))
    return ""

def print_results(query: str, results: List[Dict], mode: str):
    print(f"\n🔎 질의: {query}")
    if not results:
        print("결과가 없습니다.")
        return
    for i, b in enumerate(results, 1):
        line = f"{i}. {b.get('title','(제목없음)')}"
        if b.get("author"):
            line += f" / {b['author']}"
        line += fmt_score(b, mode)
        print(line)
        # 내용 요약 1~2줄
        if b.get("content"):
            snippet = str(b["content"]).strip().replace("\n", " ")
            if len(snippet) > 140:
                snippet = snippet[:140] + "..."
            print(f"   - {snippet}")

def main():
    args = parse_args()

    # core.retriever 임포트 (BookRetriever가 점수 필드들을 내려주도록 백엔드가 수정되어 있어야 함)
    try:
        from core.retriever import BookRetriever
    except Exception as e:
        print("❌ core.retriever.BookRetriever 임포트 실패:", e)
        sys.exit(1)

    if not os.path.isdir(args.index_dir):
        print(f"❌ 인덱스 폴더가 없습니다: {args.index_dir}")
        print("   먼저 `python build_index.py`로 인덱스를 생성하세요.")
        sys.exit(1)

    retriever = BookRetriever(index_dir=args.index_dir)

    # 단일 실행 모드
    if args.query:
        results = retriever.retrieve(args.query, top_k=args.top_k)
        print_results(args.query, results, args.mode)
        return

    # 인터랙티브 모드
    print("AI 도서 추천 빠른 검색 (종료: exit/quit)")
    while True:
        try:
            q = input("\n질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break
        if not q:
            continue
        if q.lower() in ("exit", "quit"):
            print("종료합니다.")
            break
        results = retriever.retrieve(q, top_k=args.top_k)
        print_results(q, results, args.mode)

if __name__ == "__main__":
    main()
