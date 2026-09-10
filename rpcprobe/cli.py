"""command line entry point: rpcprobe [--only publicnode,drpc] [--rpc URL] [--json] [--summary-append data/daily.csv]"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone

from . import __version__
from .endpoints import ENDPOINTS, pick
from .probe import LOG_SPANS, OLD_BLOCK, Result, measure_lag, probe

SUMMARY_FIELDS = ("date_utc", "endpoint", "url", "ok", "error", "latency_ms", "lag", "logs_range", "archive", "batch",
                  "fee_history", "blob_base_fee", "eth_config", "browser", "client")


def yes(flag: bool) -> str:
    return "yes" if flag else "no"


def summary_rows(date_utc: str, results: list[Result]) -> list[dict]:
    return [{"date_utc": date_utc, "endpoint": r.name, "url": r.url, "ok": int(r.ok), "error": r.error or "",
             "latency_ms": f"{r.latency_ms:.0f}" if r.latency_ms is not None else "", "lag": "" if r.lag is None else r.lag,
             "logs_range": r.logs_range, "archive": int(r.archive), "batch": int(r.batch), "fee_history": r.fee_history,
             "blob_base_fee": int(r.blob_base_fee), "eth_config": int(r.eth_config), "browser": int(r.browser), "client": r.client or ""}
            for r in results]


def append_summary(path: str, rows: list[dict]) -> None:
    """one row per (date, endpoint): a rerun on the same utc day replaces that day's rows."""
    existing: list[dict] = []
    if os.path.exists(path) and os.path.getsize(path):
        with open(path, newline="", encoding="utf-8") as f:
            existing = [r for r in csv.DictReader(f) if r.get("date_utc")]
    fresh = {(r["date_utc"], r["endpoint"]) for r in rows}
    merged = [r for r in existing if (r["date_utc"], r["endpoint"]) not in fresh] + rows
    merged.sort(key=lambda r: (r["date_utc"], r["endpoint"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged)


def table(results: list[Result], when: datetime) -> str:
    good = sorted((r for r in results if r.ok), key=lambda r: (r.latency_ms or 0, r.name))
    bad = [r for r in results if not r.ok]
    head = max((r.head for r in good if r.head), default=None)
    lines = [f"public ethereum rpcs, checked {when:%Y-%m-%d %H:%M} utc from this machine: {len(good)} of {len(results)} answer"
             + (f", head {head:,}" if head else ""), ""]
    if good:
        lines.append(f"{'endpoint':<12} {'p50 ms':>6} {'lag':>4} {'logs':>7} {'archive':>7} {'batch':>5} {'fee hist':>8} "
                     f"{'blob fee':>8} {'eth_config':>10} {'browser':>7}  client")
        for r in good:
            lag = "?" if r.lag is None else str(r.lag)
            logs = f"{r.logs_range:,}" if r.logs_range else "-"
            cells = (f"{r.name[:12]:<12} {r.latency_ms:>6.0f} {lag:>4} {logs:>7} {yes(r.archive):>7} {yes(r.batch):>5} "
                     f"{r.fee_history or '-':>8} {yes(r.blob_base_fee):>8} {yes(r.eth_config):>10} {yes(r.browser):>7}")
            lines.append(f"{cells}  {r.client or ''}".rstrip())
    if bad:
        lines += ["", "no answer, or not without an account:"]
        lines += [f"  {r.name:<12} {r.error}" for r in bad]
    lines += ["", "p50: median of five eth_blockNumber round trips from here. lag: blocks behind the highest head, read at one moment.",
              f"logs: the widest range of blocks answered for one address and one event (tried {', '.join(f'{s:,}' for s in LOG_SPANS)}).",
              f"archive: an address's balance at block {OLD_BLOCK:,}. browser: the answer carries access-control-allow-origin."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="rpcprobe", description="which public ethereum rpcs answer, and what they let you do. no keys.")
    ap.add_argument("--only", metavar="NAMES", help="comma separated endpoint names (default: all built-in ones; --list shows them)")
    ap.add_argument("--rpc", action="append", metavar="URL", help="check this endpoint as well (repeatable)")
    ap.add_argument("--timeout", type=float, default=15.0, help="seconds per request (default 15)")
    ap.add_argument("--workers", type=int, default=3, help="endpoints checked at the same time (default 3)")
    ap.add_argument("--json", action="store_true", help="json instead of the table")
    ap.add_argument("--csv", metavar="FILE", help="the results as a csv file")
    ap.add_argument("--summary-append", metavar="PATH", help="one row per endpoint appended to a csv (one set per utc date)")
    ap.add_argument("--quiet", action="store_true", help="no table on stdout")
    ap.add_argument("--list", action="store_true", help="print the built-in endpoints and exit")
    ap.add_argument("--version", action="version", version=f"rpcprobe {__version__}")
    args = ap.parse_args(argv)

    if args.list:
        for e in ENDPOINTS:
            print(f"{e.name:<12} {e.url}")
        return 0
    try:
        chosen = pick(args.only, args.rpc)
    except KeyError as exc:
        print(f"error: unknown endpoint {exc}; --list shows the names", file=sys.stderr)
        return 2
    if args.workers < 1 or args.timeout <= 0:
        print("error: --workers and --timeout want a positive number", file=sys.stderr)
        return 2

    when = datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda e: probe(e.name, e.url, args.timeout), chosen))
    measure_lag(results, args.timeout)

    if args.summary_append:
        append_summary(args.summary_append, summary_rows(when.strftime("%Y-%m-%d"), results))
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(summary_rows(when.strftime("%Y-%m-%d"), results))
    if args.quiet:
        return 0 if any(r.ok for r in results) else 2
    if args.json:
        print(json.dumps({"checked_utc": when.isoformat(timespec="seconds"),
                          "endpoints": [{**asdict(r), "browser": r.browser} for r in results]}, indent=2))
    else:
        print(table(results, when))
    return 0 if any(r.ok for r in results) else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
