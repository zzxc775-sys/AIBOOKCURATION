# backend/bench_recommend.py (fixed)

import argparse
import time
import statistics as stats
import requests


def percentile(xs, p):
    xs = sorted(xs)
    if not xs:
        return 0.0
    k = (len(xs) - 1) * p
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return xs[f]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8000/recommend")
    p.add_argument("--query", default="일에 잘 몰입할 수 있는 방법을 알려주는 책을 소개해줘")
    p.add_argument("--topk", type=int, default=5)
    p.add_argument("--n", type=int, default=10, help="반복 횟수")
    p.add_argument("--timeout", type=float, default=120.0)
    args = p.parse_args()

    latencies = []
    ok = 0
    fail = 0

    for i in range(1, args.n + 1):
        payload = {"query": args.query, "top_k": args.topk}
        t0 = time.perf_counter()

        r = None
        j = None
        status_code = None
        search_sec = None
        llm_sec = None
        llm_err = None
        has_summary = False
        results_len = 0

        try:
            r = requests.post(args.url, json=payload, timeout=args.timeout)
            dt = time.perf_counter() - t0
            latencies.append(dt)
            status_code = r.status_code

            # JSON 파싱은 "가능할 때만" (서버가 에러 HTML을 줄 수도 있음)
            try:
                j = r.json()
            except Exception:
                j = None

            if r.ok and isinstance(j, dict):
                ok += 1

                # content가 존재하는지 / null인지 구분 가능하게
                has_content_key = ("content" in j)
                content_val = j.get("content") if has_content_key else None
                has_summary = bool(content_val)  # None/"" 모두 False

                results = j.get("results") or []
                results_len = len(results) if isinstance(results, list) else 0

                dbg = j.get("debug") or {}
                search_sec = dbg.get("search_sec")
                llm_sec = dbg.get("llm_sec")
                llm_err = dbg.get("llm_error")

                # 원하는 경우 아래를 print에 추가해서 null 여부까지 확인 가능
                # content_is_null = (content_val is None) if has_content_key else None
                # content_is_empty = (content_val == "") if has_content_key else None

            else:
                # HTTP 에러거나 JSON이 dict가 아니면 fail로 집계
                fail += 1

            print(
                f"[{i:02d}] {dt:6.2f}s | status={status_code} | "
                f"summary={has_summary} | results={results_len} | "
                f"search_sec={search_sec} | llm_sec={llm_sec} | "
                f"llm_err={('yes' if llm_err else 'no')}"
            )

        except Exception as e:
            dt = time.perf_counter() - t0
            latencies.append(dt)
            fail += 1
            # 여기서는 r이 없을 수 있으니 status_code 같은 거 찍지 말고 예외만 출력
            print(f"[{i:02d}] {dt:6.2f}s | EXCEPTION: {repr(e)}")

    if latencies:
        print("\n=== Summary ===")
        print(f"ok={ok}, fail={fail}")
        print(
            f"mean={stats.mean(latencies):.2f}s, "
            f"median={stats.median(latencies):.2f}s, "
            f"p90={percentile(latencies, 0.90):.2f}s, "
            f"p95={percentile(latencies, 0.95):.2f}s, "
            f"max={max(latencies):.2f}s"
        )


if __name__ == "__main__":
    main()
