"""Safely compare TAB_POOL_SIZE=1 vs 2 for AutoBot's seven browser profiles.

This harness launches a temporary, isolated Microsoft Edge profile and uses the
project's real TabPool acquire logic. It measures startup prewarm, tab acquire,
necessary navigation, and readiness through input-field discovery. It NEVER
fills username/code fields and NEVER clicks a submit button. Therefore the
result is a pre-submit latency proxy, not a real server-side total_submit_ms.

Run from the AutoBot project root with its virtual environment:
    .\\.venv312\\Scripts\\python.exe .\\benchmark_tab_pool.py --rounds 4

Use --domains to reduce traffic, e.g. --domains tangquaqq88.com,livemm88.net.
Use --headless only if the target sites behave correctly in headless Edge.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_ACCOUNT_COUNTS = {
    "tangquaqq88.com": 1,
    "hi88-freecode.pages.dev": 1,
    "livemm88.net": 2,
    "rr88code.com": 2,
    "xx88code.com": 2,
    "gg88live.tv": 2,
    "o8code.com": 1,
}


def percentile(values: list[float], p: float) -> float | None:
    """Linear-interpolated percentile, including for a one-sample group."""
    vals = sorted(float(v) for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return round(vals[0], 2)
    pos = (len(vals) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    frac = pos - lo
    return round(vals[lo] * (1 - frac) + vals[hi] * frac, 2)


def parse_domain_int(items: list[str], option_name: str) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"{option_name} expects DOMAIN=VALUE, got: {item!r}")
        domain, raw_value = item.split("=", 1)
        value = int(raw_value)
        if value < 1:
            raise ValueError(f"{option_name} values must be >= 1: {item!r}")
        parsed[domain.strip().lower()] = value
    return parsed


def edge_tree_rss_mb(user_data_dir: Path) -> float | None:
    """Best-effort RSS for the isolated Edge process tree; requires psutil."""
    try:
        import psutil  # type: ignore

        needle = os.path.normcase(str(user_data_dir.resolve()))
        processes = {}
        children: dict[int, list[int]] = defaultdict(list)
        roots: list[int] = []
        for proc in psutil.process_iter(["pid", "ppid", "cmdline"]):
            try:
                info = proc.info
                pid = int(info["pid"])
                ppid = int(info.get("ppid") or 0)
                processes[pid] = proc
                children[ppid].append(pid)
                cmd = os.path.normcase(" ".join(info.get("cmdline") or []))
                if needle and needle in cmd:
                    roots.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError, ValueError):
                continue
        seen: set[int] = set()
        stack = list(roots)
        while stack:
            pid = stack.pop()
            if pid in seen:
                continue
            seen.add(pid)
            stack.extend(children.get(pid, ()))
        total = 0
        for pid in seen:
            proc = processes.get(pid)
            if proc is None:
                continue
            try:
                total += proc.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return round(total / (1024 * 1024), 1) if total else None
    except Exception:
        return None


def build_summary(rows: list[dict]) -> dict:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("outcome") == "ok" and row.get("phase") in {"first_burst", "steady_burst"}:
            groups[(row["tab_pool_size"], row["phase"])].append(row)
    summary = {}
    for (pool_size, phase), items in sorted(groups.items()):
        summary[f"TAB_POOL_SIZE={pool_size}/{phase}"] = {
            "samples": len(items),
            "tab_acquire_p50_ms": percentile([r["tab_acquire_ms"] for r in items if r.get("tab_acquire_ms") is not None], 0.50),
            "tab_acquire_p95_ms": percentile([r["tab_acquire_ms"] for r in items if r.get("tab_acquire_ms") is not None], 0.95),
            "submit_ready_proxy_p50_ms": percentile([r["submit_ready_ms"] for r in items if r.get("submit_ready_ms") is not None], 0.50),
            "submit_ready_proxy_p95_ms": percentile([r["submit_ready_ms"] for r in items if r.get("submit_ready_ms") is not None], 0.95),
            "navigation_p95_ms": percentile([r["navigation_ms"] for r in items if r.get("navigation_ms") is not None], 0.95),
        }
    return summary


async def run_configuration(
    *,
    playwright,
    engine,
    Config,
    profiles,
    domains: list[str],
    target_urls: dict[str, str],
    tab_pool_size: int,
    account_counts: dict[str, int],
    rounds: int,
    global_limit: int,
    headless: bool,
    idle_wait_seconds: int,
) -> tuple[dict, list[dict]]:
    user_data_dir = Path(tempfile.mkdtemp(prefix=f"autobot-tabbench-{tab_pool_size}-"))
    context = None
    rows: list[dict] = []
    started_browser = time.perf_counter()
    try:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            channel="msedge",
            headless=headless,
            viewport={"width": 1365, "height": 900},
            args=["--no-first-run", "--disable-session-crashed-bubble"],
        )
        browser_start_ms = round((time.perf_counter() - started_browser) * 1000, 2)

        # Keep any lazy-created tabs inside the temporary test profile. The
        # bot's configured production Edge/CDP profile is never connected.
        async def isolated_context(*_args, **_kwargs):
            return context

        engine.get_or_launch_browser_context = isolated_context
        Config.TAB_POOL_SIZE = tab_pool_size

        domain_caps: dict[str, int] = {}
        for domain in domains:
            profile = profiles[domain]
            configured_count = account_counts.get(
                domain, DEFAULT_ACCOUNT_COUNTS.get(domain, profile.tab_slots)
            )
            domain_caps[domain] = min(
                max(1, int(getattr(Config, "MAX_TAB_PER_DOMAIN_CAP", 5))),
                max(1, int(profile.tab_slots)),
                max(1, int(configured_count)),
            )

        pool = engine.TabPool(max_per_domain=tab_pool_size, per_domain_overrides=domain_caps)
        setup_semaphore = asyncio.Semaphore(8)
        navigation_semaphore = asyncio.Semaphore(5)
        pool_pages = []
        warm_plan = [
            (domain, slot)
            for domain in domains
            for slot in range(min(domain_caps[domain], tab_pool_size))
        ]
        prewarm_start = time.perf_counter()

        async def setup_page(domain: str, slot: int):
            async with setup_semaphore:
                page = await context.new_page()
                await engine._setup_page_performance(page, f"tabbench-{tab_pool_size}-{domain}-{slot}")
                entry = pool._new_entry(page)
                pool._domains.setdefault(domain, []).append(entry)
                pool._rr_idx.setdefault(domain, 0)
                pool_pages.append(page)
                return domain, slot, page

        prepared = await asyncio.gather(*(setup_page(domain, slot) for domain, slot in warm_plan))

        async def navigate_warm_page(domain: str, slot: int, page):
            started = time.perf_counter()
            error = ""
            try:
                async with navigation_semaphore:
                    await page.goto(
                        target_urls[domain],
                        wait_until="domcontentloaded",
                        timeout=max(1000, int(getattr(Config, "PAGE_NAVIGATION_TIMEOUT", 10000))),
                    )
            except Exception as exc:
                error = type(exc).__name__
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            return {"domain": domain, "slot": slot, "navigation_ms": elapsed, "error": error}

        nav_results = await asyncio.gather(*(
            navigate_warm_page(domain, slot, page) for domain, slot, page in prepared
        ))
        prewarm_ms = round((time.perf_counter() - prewarm_start) * 1000, 2)
        prewarm_errors = [r for r in nav_results if r["error"]]
        rss_after_prewarm = edge_tree_rss_mb(user_data_dir)
        rows.append({
            "tab_pool_size": tab_pool_size,
            "phase": "prewarm",
            "domain": "__all__",
            "iteration": 0,
            "slot": 0,
            "queue_wait_ms": 0.0,
            "tab_acquire_ms": None,
            "navigation_ms": prewarm_ms,
            "submit_ready_ms": prewarm_ms,
            "outcome": "ok" if not prewarm_errors else "partial",
            "error": f"{len(prewarm_errors)} navigation error(s)" if prewarm_errors else "",
            "pool_tabs_after": len(pool_pages),
            "edge_rss_mb": rss_after_prewarm,
        })

        global_semaphore = asyncio.Semaphore(max(1, global_limit))

        async def prepare_one(domain: str, slot: int, phase: str, iteration: int):
            task_started = time.perf_counter()
            acquired_global = time.perf_counter()
            try:
                async with global_semaphore:
                    after_global = time.perf_counter()
                    queue_wait_ms = (after_global - acquired_global) * 1000
                    acquire_started = time.perf_counter()
                    entry, page, tab_lock = await pool.acquire(domain=domain)
                    tab_acquire_ms = (time.perf_counter() - acquire_started) * 1000
                    navigation_ms = 0.0
                    async with tab_lock:
                        # Mirror submit_code_browser's reservation release. No
                        # account/code is supplied and no submit button is used.
                        entry["reserved"] = False
                        nav_started = time.perf_counter()
                        if not engine._page_matches_target(page.url, target_urls[domain], domain):
                            await page.goto(
                                target_urls[domain],
                                wait_until="domcontentloaded",
                                timeout=max(1000, int(getattr(Config, "PAGE_NAVIGATION_TIMEOUT", 10000))),
                            )
                            if domain == "livemm88.net":
                                await engine.open_mm88_code_form(page)
                            await engine.scroll_to_input_fields(page)
                            settle = float(getattr(profiles[domain], "form_settle_seconds", 0.03))
                            if settle > 0:
                                await asyncio.sleep(settle)
                        navigation_ms = (time.perf_counter() - nav_started) * 1000
                        await page.bring_to_front()
                        input_key = f"tabbench-{tab_pool_size}-{domain}-{id(page)}"
                        _username_input, code_input = await engine.find_input_fields(
                            page, cache_key=input_key, domain=domain
                        )
                        if not code_input and domain == "livemm88.net":
                            await engine.open_mm88_code_form(page)
                            _username_input, code_input = await engine.find_input_fields(
                                page, cache_key=input_key, domain=domain
                            )
                        if not code_input:
                            raise RuntimeError("code input not found; page may be challenged or UI changed")
                    entry["reserved"] = False
                    total_ms = (time.perf_counter() - task_started) * 1000
                    rss = edge_tree_rss_mb(user_data_dir)
                    return {
                        "tab_pool_size": tab_pool_size,
                        "phase": phase,
                        "domain": domain,
                        "iteration": iteration,
                        "slot": slot,
                        "queue_wait_ms": round(queue_wait_ms, 2),
                        "tab_acquire_ms": round(tab_acquire_ms, 2),
                        "navigation_ms": round(navigation_ms, 2),
                        "submit_ready_ms": round(total_ms, 2),
                        "outcome": "ok",
                        "error": "",
                        "pool_tabs_after": sum(len(v) for v in pool._domains.values()),
                        "edge_rss_mb": rss,
                    }
            except Exception as exc:
                if "entry" in locals():
                    entry["reserved"] = False
                total_ms = (time.perf_counter() - task_started) * 1000
                return {
                    "tab_pool_size": tab_pool_size,
                    "phase": phase,
                    "domain": domain,
                    "iteration": iteration,
                    "slot": slot,
                    "queue_wait_ms": None,
                    "tab_acquire_ms": None,
                    "navigation_ms": None,
                    "submit_ready_ms": round(total_ms, 2),
                    "outcome": "error",
                    "error": type(exc).__name__,
                    "pool_tabs_after": sum(len(v) for v in pool._domains.values()),
                    "edge_rss_mb": edge_tree_rss_mb(user_data_dir),
                }

        # One task for each profile slot; a two-slot domain therefore tests the
        # first parallel burst where TAB_POOL_SIZE=1 must lazy-open slot two.
        for iteration in range(1, rounds + 1):
            phase = "first_burst" if iteration == 1 else "steady_burst"
            tasks = [
                (domain, slot)
                for domain in domains
                for slot in range(domain_caps[domain])
            ]
            # Stable but non-domain-grouped order reduces systematic bias under
            # the global submit semaphore when there are more slots than workers.
            random.Random(2026 + iteration).shuffle(tasks)
            batch = await asyncio.gather(*(
                prepare_one(domain, slot, phase, iteration) for domain, slot in tasks
            ))
            rows.extend(batch)
            rss = edge_tree_rss_mb(user_data_dir)
            rows.append({
                "tab_pool_size": tab_pool_size,
                "phase": f"{phase}_snapshot",
                "domain": "__all__",
                "iteration": iteration,
                "slot": 0,
                "queue_wait_ms": 0.0,
                "tab_acquire_ms": None,
                "navigation_ms": 0.0,
                "submit_ready_ms": 0.0,
                "outcome": "ok",
                "error": "",
                "pool_tabs_after": sum(len(v) for v in pool._domains.values()),
                "edge_rss_mb": rss,
            })

        rss_after_bursts = edge_tree_rss_mb(user_data_dir)
        idle_gc_metadata = None
        if idle_wait_seconds > 0:
            print(
                f"  Chờ {idle_wait_seconds}s để giả lập idle; "
                "sau đó chạy GC theo TAB_POOL_IDLE_TTL/MIN_TABS_PER_DOMAIN..."
            )
            await asyncio.sleep(idle_wait_seconds)
            gc_stats = await pool.collect_garbage(
                idle_ttl=float(getattr(Config, "TAB_POOL_IDLE_TTL", 900.0)),
                min_tabs_per_domain=int(getattr(Config, "TAB_POOL_MIN_TABS_PER_DOMAIN", 2)),
            )
            await asyncio.sleep(2.0)
            rss_after_gc = edge_tree_rss_mb(user_data_dir)
            tabs_after_gc = sum(len(v) for v in pool._domains.values())
            idle_gc_metadata = {
                "gc_stats": gc_stats,
                "tabs_after_gc": tabs_after_gc,
                "edge_rss_mb_after_gc": rss_after_gc,
            }
            rows.append({
                "tab_pool_size": tab_pool_size,
                "phase": "idle_gc_snapshot",
                "domain": "__all__",
                "iteration": rounds,
                "slot": 0,
                "queue_wait_ms": 0.0,
                "tab_acquire_ms": None,
                "navigation_ms": 0.0,
                "submit_ready_ms": 0.0,
                "outcome": "ok",
                "error": "",
                "pool_tabs_after": tabs_after_gc,
                "edge_rss_mb": rss_after_gc,
            })

        metadata = {
            "tab_pool_size": tab_pool_size,
            "browser_startup_ms": browser_start_ms,
            "prewarm_ms": prewarm_ms,
            "prewarm_tab_count": len(pool_pages),
            "account_counts_assumed": {
                domain: account_counts.get(domain, DEFAULT_ACCOUNT_COUNTS.get(domain, profiles[domain].tab_slots))
                for domain in domains
            },
            "effective_domain_caps": domain_caps,
            "edge_rss_mb_after_prewarm": rss_after_prewarm,
            "edge_rss_mb_after_bursts": rss_after_bursts,
            "idle_gc": idle_gc_metadata,
            "prewarm_navigation_errors": len(prewarm_errors),
            "isolated_user_data_dir": True,
            "real_submits_performed": 0,
        }
        return metadata, rows
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        try:
            import shutil
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass


async def async_main(args) -> int:
    sys.path.insert(0, str(PROJECT_DIR))
    try:
        from playwright.async_api import async_playwright
        import browser_engine as engine
        from browser_site_profiles import SITE_PROFILES
        from config import Config
    except Exception as exc:
        print(f"Không import được dependency/project module: {type(exc).__name__}: {exc}")
        print("Hãy chạy bằng Python trong .venv312 của AutoBot.")
        return 2

    domains = [d.strip().lower() for d in args.domains.split(",") if d.strip()]
    unknown = [d for d in domains if d not in SITE_PROFILES]
    if unknown:
        print("Profile không hợp lệ: " + ", ".join(unknown))
        print("Profiles: " + ", ".join(sorted(SITE_PROFILES)))
        return 2

    account_counts = parse_domain_int(args.account_count, "--account-count")
    url_overrides = {}
    for value in args.url:
        if "=" not in value:
            raise ValueError("--url expects DOMAIN=URL")
        domain, url = value.split("=", 1)
        url_overrides[domain.strip().lower()] = url.strip()

    configured_urls = getattr(Config, "DOMAIN_TO_CHANNEL_URL", {}) or {}
    target_urls = {}
    for domain in domains:
        profile = SITE_PROFILES[domain]
        target = url_overrides.get(domain) or configured_urls.get(domain) or profile.origin
        host = (urlparse(target).hostname or "").lower().removeprefix("www.")
        if host != domain:
            print(f"URL sai host cho {domain}; không mở trang: {target}")
            return 2
        target_urls[domain] = target

    rounds = max(1, args.rounds)
    global_limit = max(1, args.global_concurrency or int(getattr(Config, "MAX_CONCURRENT_SUBMITS", 8)))
    sizes = [int(x) for x in args.size_order.split(",")]
    if sorted(sizes) != [1, 2]:
        print("--size-order chỉ nhận 1,2 hoặc 2,1")
        return 2

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_all = []
    rows_all = []
    async with async_playwright() as playwright:
        for size in sizes:
            print(f"\n[Benchmark] TAB_POOL_SIZE={size}: Edge isolated, không submit thật...")
            metadata, rows = await run_configuration(
                playwright=playwright,
                engine=engine,
                Config=Config,
                profiles=SITE_PROFILES,
                domains=domains,
                target_urls=target_urls,
                tab_pool_size=size,
                account_counts=account_counts,
                rounds=rounds,
                global_limit=global_limit,
                headless=args.headless,
                idle_wait_seconds=args.idle_wait_seconds,
            )
            metadata_all.append(metadata)
            rows_all.extend(rows)
            print(
                f"  prewarm={metadata['prewarm_ms']:.0f} ms, "
                f"tabs={metadata['prewarm_tab_count']}, "
                f"Edge RSS after prewarm={metadata['edge_rss_mb_after_prewarm']} MB, "
                f"RSS after bursts={metadata['edge_rss_mb_after_bursts']} MB"
            )

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "domains": domains,
        "rounds": rounds,
        "global_concurrency": global_limit,
        "warning": "submit_ready_ms is a pre-submit proxy; no real submit button was clicked.",
        "configurations": metadata_all,
        "latency_summary": build_summary(rows_all),
    }
    csv_path = output_dir / "tab_pool_benchmark.csv"
    json_path = output_dir / "tab_pool_benchmark_summary.json"
    columns = [
        "tab_pool_size", "phase", "domain", "iteration", "slot",
        "queue_wait_ms", "tab_acquire_ms", "navigation_ms", "submit_ready_ms",
        "outcome", "error", "pool_tabs_after", "edge_rss_mb",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_all)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nLatency summary (successful samples):")
    print(json.dumps(summary["latency_summary"], ensure_ascii=False, indent=2))
    print(f"\nCSV: {csv_path}")
    print(f"JSON: {json_path}")
    print("Lưu ý: so sánh này đo tab/pre-submit readiness, không đo response server sau khi bấm submit.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe AutoBot TAB_POOL_SIZE 1 vs 2 benchmark")
    parser.add_argument(
        "--domains",
        default="",
        help="Danh sách domain, ngăn cách dấu phẩy; mặc định là cả 7 profile.",
    )
    parser.add_argument("--rounds", type=int, default=4, help="Số burst/domain cho mỗi cấu hình (>=1).")
    parser.add_argument("--idle-wait-seconds", type=int, default=0, help="Tuỳ chọn: chờ rồi đo GC idle; đặt >= TAB_POOL_IDLE_TTL để kiểm tra thu hồi tab.")
    parser.add_argument("--global-concurrency", type=int, default=0, help="Mặc định dùng MAX_CONCURRENT_SUBMITS từ Config.")
    parser.add_argument("--account-count", action="append", default=[], metavar="DOMAIN=N", help="Giới hạn slot theo số target accounts; có thể lặp lại.")
    parser.add_argument("--url", action="append", default=[], metavar="DOMAIN=URL", help="Override URL để dùng path form production/staging; có thể lặp lại.")
    parser.add_argument("--size-order", default="1,2", help="Thứ tự chạy để giảm bias; dùng 2,1 ở lượt xác nhận thứ hai.")
    parser.add_argument("--headless", action="store_true", help="Chỉ bật nếu các site chạy ổn định ở headless Edge.")
    parser.add_argument("--output", default=str(PROJECT_DIR / "benchmark_results"), help="Thư mục chứa CSV/JSON kết quả.")
    args = parser.parse_args()

    if not args.domains:
        # Lazy import keeps percentile/summary helpers testable without Edge.
        sys.path.insert(0, str(PROJECT_DIR))
        try:
            from browser_site_profiles import SITE_PROFILES
            args.domains = ",".join(sorted(SITE_PROFILES))
        except Exception as exc:
            print(f"Không đọc được browser_site_profiles.py: {type(exc).__name__}: {exc}")
            return 2
    if args.rounds < 1:
        parser.error("--rounds phải >= 1")
    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\nĐã dừng benchmark; Edge test profile sẽ được đóng khi thoát.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
