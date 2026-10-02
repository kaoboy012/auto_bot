#!/usr/bin/env python3
"""Summarize production OCR timing logs by cache status and site.

Usage:
    python production_ocr_metrics.py bot.log
    journalctl -u giftcode-bot --since today | python production_ocr_metrics.py -
"""
from __future__ import annotations

import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

LINE_RE = re.compile(
    r"OCR-TIMING.*?domain=(?P<domain>\S+) total_ms=(?P<total>[-\d.]+) "
    r"ocr_ms=(?P<ocr>\S+) download_ms=(?P<download>\S+) .*?"
    r"cache_status=(?P<cache>\S+) media_id=(?P<media>\S+)"
)


def percentile(values: list[float], p: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int((len(values) - 1) * p)))
    return values[index]


def metric(values: list[float]) -> str:
    if not values:
        return "n/a"
    return f"n={len(values)} p50={statistics.median(values):.1f}ms p95={percentile(values, .95):.1f}ms"


def main() -> int:
    source = sys.stdin if len(sys.argv) < 2 or sys.argv[1] == "-" else Path(sys.argv[1]).open(encoding="utf-8", errors="replace")
    groups: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    media_status: dict[str, list[str]] = defaultdict(list)
    parsed = 0
    try:
        for line in source:
            match = LINE_RE.search(line)
            if not match:
                continue
            parsed += 1
            data = match.groupdict()
            key = (data["domain"], data["cache"])
            for field in ("total", "ocr", "download"):
                value = data[field]
                if value not in {"n/a", "None", ""}:
                    try:
                        groups[key][field].append(float(value))
                    except ValueError:
                        pass
            media_status[data["media"]].append(data["cache"])
    finally:
        if source is not sys.stdin:
            source.close()

    print(f"parsed_timing_lines={parsed}")
    for (domain, cache), values in sorted(groups.items()):
        print(
            f"domain={domain} cache={cache} "
            f"total[{metric(values['total'])}] "
            f"download[{metric(values['download'])}] "
            f"ocr[{metric(values['ocr'])}]"
        )
    # A normal redelivery sequence is MISS followed by one or more HITs.
    # Flag a HIT before the first MISS, or a MISS after a HIT.
    inconsistent = {
        media: statuses
        for media, statuses in media_status.items()
        if statuses and (statuses[0] == "hit" or "miss" in statuses[1:])
    }
    print(f"unique_media_ids={len(media_status)} invalid_cache_sequences={len(inconsistent)}")
    if inconsistent:
        for media, statuses in sorted(inconsistent.items()):
            print(f"WARNING media_id={media} sequence={','.join(statuses)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
