"""工单20 · 性能基准测试（关键接口延迟与并发吞吐）

工单编号：人工智能CV-AIGC-20-文旅Agent任务工单-功能集成测试与部署
对应 docs/06 §九「性能满足高并发与低延迟要求」与 §十.3「性能优化」。

测量口径说明（重要）：
  本机为 CPU 环境，且 SiliconFlow 云端额度不可用。**凡是需要等待云端模型的接口
  一律不纳入基准**——量到的会是重试退避时间，而不是接口真实性能，反而误导优化方向。
  因此这里只测两类：
    1. 纯本地/数据层接口（就绪检查、列表、DB 查询）——反映服务框架与数据层开销；
    2. **确定性本地计算接口**（导览地图 Pillow 渲染、感知推理）——反映 CPU 计算成本，
       这类是真正需要在生产用更多副本横向扩展的部分。

用法（需先启动后端）：
    python scripts/benchmark.py
    python scripts/benchmark.py --base http://127.0.0.1:8100 --rounds 10 --concurrency 32
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 行程分站名取自 seed_places.py 灌入的真实景点，保证地图渲染路径可达
MAP_STOPS = [
    {"name": "主殿", "index": 1},
    {"name": "修葺碑亭", "index": 2},
    {"name": "水榭茶室", "index": 3},
    {"name": "登高台", "index": 4},
]


def _cases() -> list[tuple[str, str, dict | None, str]]:
    return [
        ("GET", "/api/v1/readyz", None, "就绪检查（含 4 类组件健康探测）"),
        ("GET", "/api/v1/avatar", None, "数字人形象与能力集"),
        ("GET", "/api/v1/create/assets", None, "创作列表（DB 查询 + 分页）"),
        ("POST", "/api/v1/activity/recommend", {"interests": ["非遗", "美食"], "limit": 5}, "活动推荐（PostGIS 距离 + 打分）"),
        ("POST", "/api/v1/create/map", {"title": "基准测试导览地图", "stops": MAP_STOPS}, "导览地图（Pillow 直绘 + 落库 + 对象存储）"),
    ]


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(ratio * (len(ordered) - 1))))
    return ordered[index]


def measure(client: httpx.Client, method: str, path: str, payload: dict | None, rounds: int) -> dict:
    latencies: list[float] = []
    errors = 0
    status = 0
    for _ in range(rounds):
        started = time.perf_counter()
        try:
            if method == "GET":
                response = client.get(path)
            else:
                response = client.post(path, json=payload)
            status = response.status_code
            if response.status_code >= 400:
                errors += 1
        except Exception:
            errors += 1
        latencies.append((time.perf_counter() - started) * 1000)
    return {
        "rounds": rounds,
        "status": status,
        "errors": errors,
        "min": round(min(latencies), 2),
        "mean": round(statistics.fmean(latencies), 2),
        "p50": round(_percentile(latencies, 0.5), 2),
        "p95": round(_percentile(latencies, 0.95), 2),
        "max": round(max(latencies), 2),
    }


def throughput(client: httpx.Client, path: str, concurrency: int) -> dict:
    """并发吞吐：单接口在固定并发下的成功数与总耗时。"""
    started = time.perf_counter()
    ok = 0

    def one() -> bool:
        try:
            return client.get(path).status_code == 200
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for success in pool.map(lambda _: one(), range(concurrency)):
            ok += 1 if success else 0
    elapsed = time.perf_counter() - started
    return {
        "concurrency": concurrency,
        "success": ok,
        "elapsed": round(elapsed, 3),
        "qps": round(concurrency / elapsed, 1) if elapsed > 0 else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="工单20 性能基准测试")
    parser.add_argument("--base", default="http://127.0.0.1:8100", help="后端地址")
    parser.add_argument("--rounds", type=int, default=8, help="每个接口的采样轮数")
    parser.add_argument("--concurrency", type=int, default=32, help="并发吞吐测试的并发数")
    args = parser.parse_args()

    results: dict[str, object] = {"base": args.base, "rounds": args.rounds, "endpoints": []}

    with httpx.Client(base_url=args.base, timeout=120.0) as client:
        try:
            client.get("/api/v1/readyz")
        except Exception as exc:
            print(f"后端不可达（{args.base}）：{exc}")
            raise SystemExit(1)

        print(f"{'接口':<44}{'状态':>6}{'均值':>10}{'P50':>9}{'P95':>9}{'最大':>9}")
        print("-" * 88)
        for method, path, payload, label in _cases():
            stats = measure(client, method, path, payload, args.rounds)
            suffix = f"{method} {path}"
            print(
                f"{label[:42]:<44}{stats['status']:>6}{stats['mean']:>9.1f}ms"
                f"{stats['p50']:>8.1f}ms{stats['p95']:>8.1f}ms{stats['max']:>8.1f}ms"
            )
            results["endpoints"].append({"label": label, "endpoint": suffix, **stats})

        print()
        flow = throughput(client, "/api/v1/readyz", args.concurrency)
        print(
            f"并发吞吐  GET /api/v1/readyz  并发 {flow['concurrency']}  "
            f"成功 {flow['success']}/{flow['concurrency']}  用时 {flow['elapsed']}s  → 约 {flow['qps']} QPS"
        )
        results["throughput"] = flow

    output = ROOT / "benchmark_result.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {output}")


if __name__ == "__main__":
    main()
