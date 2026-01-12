"""
search_smoke_test.py
- 로컬에서 "진짜 topK가 잘 나오나" 확인하는 스모크 테스트 스크립트

사용 예:
  python search_smoke_test.py --query "번아웃 회복" --topk 5
  python search_smoke_test.py --interactive
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from core.retriever_v2 import BookRetrieverV2


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INDEX_DIR = BASE_DIR / "models" / "faiss_index_v2"


def print_results(query: str, results: list[dict]) -> None:
    print("\n" + "=" * 70)
    print(f"🔎 QUERY: {query}")
    print("=" * 70)
    if not results:
        print("😢 결과 없음")
        return

    for i, r in enumerate(results, start=1):
        print(f"\n{i}. {r.get('title', '')}")
        print(f"   👤 {r.get('author', '')}")
        # description은 길 수 있으니 일부만
        desc = (r.get("description") or "").strip()
        preview = (desc[:160] + "...") if len(desc) > 160 else desc
        print(f"   📖 {preview}")
        if "score" in r:
            print(f"   ⭐ score(cos≈): {r['score']:.4f} | distance(L2^2): {r.get('distance')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index_dir", type=str, default=str(DEFAULT_INDEX_DIR))
    ap.add_argument("--query", type=str, default="")
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--interactive", action="store_true")
    args = ap.parse_args()

    r = BookRetrieverV2(index_dir=args.index_dir, device="cpu")

    if args.interactive:
        while True:
            q = input("\n검색어 (종료: 빈 입력)\n> ").strip()
            if not q:
                break
            out = r.retrieve(q, top_k=args.topk)
            print_results(q, out)
        return

    if not args.query.strip():
        raise SystemExit("❌ --query 를 입력하거나 --interactive 를 사용하세요.")

    out = r.retrieve(args.query, top_k=args.topk)
    print_results(args.query, out)


if __name__ == "__main__":
    main()
