#!/usr/bin/env python3
"""Collect public external OSS PRs merged during a Japanese fiscal year."""
import argparse
import csv
import io
import json
import math
import os
import re
import sys
import tempfile
import time
from collections import Counter
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc
COLUMNS = ["repository", "pr_number", "title", "created_at", "state",
           "merged", "merged_at", "closed_at", "url"]


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fiscal_bounds(year):
    return (datetime(year, 4, 1, tzinfo=JST),
            datetime(year + 1, 4, 1, tzinfo=JST))


def current_fy(now):
    local = now.astimezone(JST)
    return local.year if local.month >= 4 else local.year - 1


class GitHub:
    def __init__(self, token=None):
        self.token = token
        self.last_search = 0

    def get(self, path, params=None):
        if not path.startswith(("/repos/", "/search/issues")):
            raise ValueError("Unsupported API path")
        if path.startswith("/search/"):
            time.sleep(max(0, 2.1 - (time.monotonic() - self.last_search)))
            self.last_search = time.monotonic()
        url = "https://api.github.com" + path
        if params:
            url += "?" + urlencode(params)
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2026-03-10",
                   "User-Agent": "external-oss-pr-collector"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        for attempt in range(5):
            try:
                with urlopen(Request(url, headers=headers), timeout=60) as response:
                    return json.load(response)
            except HTTPError as exc:
                remaining = exc.headers.get("X-RateLimit-Remaining")
                retry_after = exc.headers.get("Retry-After")
                if exc.code in (403, 429) and (remaining == "0" or retry_after or exc.code == 429):
                    reset = float(exc.headers.get("X-RateLimit-Reset", time.time() + 60))
                    delay = float(retry_after) if retry_after else max(5, reset - time.time() + 2)
                elif exc.code in (500, 502, 503, 504):
                    delay = 2 ** (attempt + 1)
                else:
                    raise RuntimeError(f"GitHub API HTTP {exc.code}: {path}") from None
            except (URLError, TimeoutError):
                delay = 2 ** (attempt + 1)
            if attempt == 4:
                raise RuntimeError(f"GitHub API retries exhausted: {path}")
            if delay > 900:
                raise RuntimeError("API rate limit requires a wait longer than 15 minutes; retry later")
            print(f"API再試行: {delay:.0f}秒待機", file=sys.stderr)
            time.sleep(delay)
        raise RuntimeError("GitHub API request failed")


def search_window(api, author, first, last, audit):
    query = (f"is:pr author:{author} is:merged is:public "
             f"merged:{first.isoformat()}..{last.isoformat()} -user:{author}")
    params = {"q": query, "per_page": 100, "sort": "created", "order": "asc"}
    result = api.get("/search/issues", params)
    for _ in range(2):
        if not result.get("incomplete_results"):
            break
        result = api.get("/search/issues", params)
    if result.get("incomplete_results") or result["total_count"] > 1000:
        if first == last:
            raise RuntimeError(f"Search incomplete or over 1000 results on {first}; CSV not updated")
        midpoint = first + (last - first) // 2
        return (search_window(api, author, first, midpoint, audit) +
                search_window(api, author, midpoint + timedelta(days=1), last, audit))
    expected = result["total_count"]
    items = result["items"]
    for page in range(2, math.ceil(expected / 100) + 1):
        other = api.get("/search/issues", {**params, "page": page})
        if other.get("incomplete_results") or other["total_count"] != expected:
            raise RuntimeError("Search changed during pagination or was incomplete; retry workflow")
        items.extend(other["items"])
    if len(items) != expected or len({x["id"] for x in items}) != expected:
        raise RuntimeError("Search count mismatch or duplicates; CSV not updated")
    audit.append({"query": query, "total_count": expected, "incomplete_results": False})
    return items


def collect(api, author, year, as_of):
    start, end = fiscal_bounds(year)
    if as_of < start:
        raise ValueError("集計日時が年度開始より前です")
    # Search in UTC dates, then filter precise Japanese fiscal-year boundaries.
    first = start.astimezone(UTC).date()
    last = min(as_of, end).astimezone(UTC).date()
    audit, items = [], {}
    cursor = first
    while cursor <= last:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        window_end = min(next_month - timedelta(days=1), last)
        for item in search_window(api, author, cursor, window_end, audit):
            items[item["id"]] = item
        cursor = window_end + timedelta(days=1)
    repositories, records = {}, {}
    for item in items.values():
        match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)", item["html_url"])
        if not match:
            raise RuntimeError("Unexpected PR URL")
        repo, number = match.group(1), int(match.group(2))
        pr = api.get(f"/repos/{repo}/pulls/{number}")
        target = pr["base"]["repo"]["full_name"]
        owner = target.split("/")[0]
        if pr["user"]["login"].casefold() != author.casefold():
            raise RuntimeError("Unexpected PR author")
        if owner.casefold() == author.casefold():
            continue
        if not pr["merged"] or not pr.get("merged_at"):
            raise RuntimeError("Search returned an unmerged PR")
        merged_at = timestamp(pr["merged_at"])
        if not (start <= merged_at < end and merged_at <= as_of):
            continue
        if target not in repositories:
            meta = api.get(f"/repos/{target}")
            if meta["private"]:
                raise RuntimeError("Search returned a private repository")
            if meta["owner"]["login"].casefold() == author.casefold():
                continue
            repositories[target] = {"owner": meta["owner"]["login"],
                                    "fork": meta["fork"],
                                    "parent": (meta.get("parent") or {}).get("full_name", "")}
        records[(target.casefold(), number)] = {
            "repository": target, "pr_number": number, "title": pr["title"],
            "created_at": pr["created_at"], "state": pr["state"],
            "merged": "true", "merged_at": pr["merged_at"],
            "closed_at": pr["closed_at"] or "", "url": pr["html_url"]}
    rows = sorted(records.values(),
                  key=lambda r: (*[x.casefold() for x in r["repository"].split("/")],
                                 r["pr_number"]))
    counts = Counter(r["repository"] for r in rows)
    summary = []
    for repo in sorted(counts, key=lambda x: tuple(p.casefold() for p in x.split("/"))):
        meta = repositories[repo]
        created = sum(start <= timestamp(r["created_at"]) < end
                      for r in rows if r["repository"] == repo)
        summary.append({"repo_owner": meta["owner"], "repository": repo,
                        "merged_pr_count": counts[repo],
                        "created_in_fy_pr_count": created,
                        "created_before_fy_pr_count": counts[repo] - created,
                        "is_fork": str(meta["fork"]).lower(),
                        "parent_repository": meta["parent"],
                        "repository_url": f"https://github.com/{repo}"})
    report = {"author": author, "fiscal_year": year, "timezone": "Asia/Tokyo",
              "period_start": start.isoformat(), "period_end_exclusive": end.isoformat(),
              "as_of": as_of.astimezone(JST).isoformat(),
              "pr_count": len(rows), "repository_count": len(counts),
              "owner_count": len({r["repo_owner"] for r in summary}),
              "search_candidates": len(items), "search_windows": audit,
              "notice": "公開・検索索引登録済みPRが対象。削除・非公開化・索引反映遅延・移管履歴による欠落は保証できません。"}
    return rows, summary, report


def csv_bytes(rows, columns):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    encoded = buffer.getvalue().encode("utf-8-sig")
    parsed = list(csv.DictReader(io.StringIO(encoded.decode("utf-8-sig"))))
    if len(parsed) != len(rows):
        raise RuntimeError("CSV round-trip validation failed")
    return encoded


def write_outputs(directory, author, year, rows, summary, report):
    directory.mkdir(parents=True, exist_ok=True)
    prefix = f"{author}_external_oss_merged_prs_fy{year}"
    summary_columns = ["repo_owner", "repository", "merged_pr_count",
                       "created_in_fy_pr_count", "created_before_fy_pr_count",
                       "is_fork", "parent_repository", "repository_url"]
    payloads = {prefix + ".csv": csv_bytes(rows, COLUMNS),
                prefix + "_by_repository.csv": csv_bytes(summary, summary_columns),
                prefix + "_report.json": (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()}
    # Finish all requests and validation before replacing any output.
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        for name, data in payloads.items():
            Path(temporary, name).write_bytes(data)
        for name in payloads:
            os.replace(Path(temporary, name), directory / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--author", default="noritaka1166")
    parser.add_argument("--fiscal-year", type=int)
    parser.add_argument("--as-of", help="YYYY-MM-DD (JST end of day) or an ISO 8601 timestamp")
    parser.add_argument("--output-dir", type=Path, default=Path("generated"))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", args.author):
        parser.error("GitHubユーザー名の形式が不正です")
    now = datetime.now(JST).replace(microsecond=0)
    as_of = now
    if args.as_of:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.as_of):
            as_of = datetime.combine(date.fromisoformat(args.as_of), dtime.max, JST)
        else:
            as_of = timestamp(args.as_of)
            if as_of.tzinfo is None:
                parser.error("--as-ofにはタイムゾーンが必要です")
        as_of = min(as_of, now)
    year = args.fiscal_year if args.fiscal_year is not None else current_fy(as_of)
    api = GitHub(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    rows, summary, report = collect(api, args.author, year, as_of)
    write_outputs(args.output_dir, args.author, year, rows, summary, report)
    message = (f"FY{year}: {len(rows)}件 / {report['repository_count']}リポジトリ / "
               f"{report['owner_count']} owner\n集計日時: {report['as_of']}\n")
    print(message)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(message + "\n" + report["notice"] + "\n")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as exc:
        print(f"集計失敗: {exc}", file=sys.stderr)
        sys.exit(1)
