# backend/bench_recommend.py
import argparse
import time
import statistics as stats
import requests

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="https://aibookcuration.onrender.com/recommend")
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
        try:
            r = requests.post(args.url, json=payload, timeout=args.timeout)
            dt = time.perf_counter() - t0
            latencies.append(dt)

            if r.ok:
                ok += 1
                j = r.json()
                # LLM이 성공하면 content가 보통 채워짐(네 코드 기준)
                has_summary = bool(j.get("content"))
                print(f"[{i:02d}] {dt:6.2f}s | status={r.status_code} | summary={has_summary} | results={len(j.get('results', []))}")
            else:
                fail += 1
                print(f"[{i:02d}] {dt:6.2f}s | status={r.status_code} | body={r.text[:200]}")
        except Exception as e:
            dt = time.perf_counter() - t0
            latencies.append(dt)
            fail += 1
            print(f"[{i:02d}] {dt:6.2f}s | EXCEPTION: {e}")

    if latencies:
        print("\n=== Summary ===")
        print(f"ok={ok}, fail={fail}")
        print(f"mean={stats.mean(latencies):.2f}s, median={stats.median(latencies):.2f}s, p90={percentile(latencies, 0.90):.2f}s, p95={percentile(latencies, 0.95):.2f}s, max={max(latencies):.2f}s")

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

if __name__ == "__main__":
    main()
