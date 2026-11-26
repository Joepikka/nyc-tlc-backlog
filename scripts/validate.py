"""Reconcile the DuckDB exports against the original NYC records."""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

START = date(2025, 1, 1)
END = date(2025, 3, 31)
SNAPSHOT = Path("data/tlc.csv")


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    manifest = json.loads(Path("data/manifest.json").read_text())
    rows = read_csv(SNAPSHOT)
    keys = {row["unique_key"] for row in rows}
    require(len(rows) == manifest["rows"] == len(keys) and "" not in keys, "Snapshot keys or row count")
    require(hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest() == manifest["sha256"], "Snapshot checksum")

    grouped = defaultdict(list)
    quality = Counter(dict.fromkeys([
        "missing_or_invalid_creation", "invalid_closure", "closure_before_creation",
        "missing_borough", "missing_problem", "closed_without_closure", "populated_due_date",
    ], 0))
    for row in rows:
        require(row["agency"] == "TLC", f"Unexpected agency for {row['unique_key']}")
        quality["missing_borough"] += not row["borough"].strip()
        quality["missing_problem"] += not row["complaint_type"].strip()
        quality["closed_without_closure"] += row["status"].strip().casefold() == "closed" and not row["closed_date"]
        quality["populated_due_date"] += bool(row["due_date"])
        try:
            opened = datetime.fromisoformat(row["created_date"])
        except ValueError:
            quality["missing_or_invalid_creation"] += 1
            continue
        try:
            closed = datetime.fromisoformat(row["closed_date"]) if row["closed_date"] else None
        except ValueError:
            quality["invalid_closure"] += 1
            continue
        if closed is not None and closed < opened:
            quality["closure_before_creation"] += 1
            continue
        require(date(2024, 1, 1) <= opened.date() <= END, f"Out-of-scope request {row['unique_key']}")
        group = row["complaint_type"].strip() or "Unknown", row["borough"].strip() or "Unknown"
        grouped[group].append((row["unique_key"], opened.date(), closed.date() if closed else None))

    daily_rows = read_csv("exports/daily.csv")
    counts = ("arrivals", "closures", "backlog", "aged30")
    daily = {
        (date.fromisoformat(row["day"]), row["problem"], row["borough"]):
            tuple(int(row[name]) for name in counts)
        for row in daily_rows
    }
    days = (END - START).days + 1
    require(len(daily) == len(daily_rows) == days * len(grouped), "Unexpected daily table grain")
    totals = Counter()
    problems = defaultdict(Counter)
    worklist = []
    timeline = defaultdict(Counter)

    for (problem, borough), requests in grouped.items():
        opening = sum(opened < START and (closed is None or closed >= START) for _, opened, closed in requests)
        previous = opening
        totals["opening"] += opening
        problems[problem]["opening"] += opening
        for offset in range(days):
            day = START + timedelta(days=offset)
            arrivals = sum(opened == day for _, opened, _ in requests)
            closures = sum(closed == day for _, _, closed in requests)
            open_requests = [(key, opened) for key, opened, closed in requests
                             if opened <= day and (closed is None or closed > day)]
            backlog = len(open_requests)
            aged30 = sum((day - opened).days >= 30 for _, opened in open_requests)
            expected = arrivals, closures, backlog, aged30
            require(daily.get((day, problem, borough)) == expected, f"Direct count mismatch for {day}, {problem}, {borough}")
            require(previous + arrivals - closures == backlog, f"Roll-forward mismatch for {day}, {problem}, {borough}")
            previous = backlog
            totals.update(arrivals=arrivals, closures=closures)
            problems[problem].update(arrivals=arrivals, closures=closures)
            timeline[day.isoformat()].update(dict(zip(counts, expected)))
            if day == END:
                totals.update(backlog=backlog, aged30=aged30)
                problems[problem].update(backlog=backlog, aged30=aged30)
                for key, opened in open_requests:
                    worklist.append(dict(unique_key=key, problem=problem, borough=borough,
                                         created_day=opened.isoformat(), age_days=str((day - opened).days)))

    worklist.sort(key=lambda row: (-int(row["age_days"]), row["unique_key"]))
    require(worklist == read_csv("exports/open_march31.csv"), "March 31 export or sort order mismatch")
    for result in [totals, *problems.values()]:
        result["net_change"] = result["arrivals"] - result["closures"]
        require(result["opening"] + result["net_change"] == result["backlog"], "Quarter roll-forward")

    report = {
        "snapshot": manifest["sha256"],
        "source_rows": len(rows),
        "excluded_rows": len(rows) - sum(map(len, grouped.values())),
        "quality": dict(quality),
        "days_reconciled": days,
        "problem_borough_groups_reconciled": len(grouped),
        "daily_rows_reconciled": len(daily),
        "quarter": dict(totals),
        "by_problem": dict(sorted(problems.items(), key=lambda item: (-item[1]["net_change"], item[0]))),
        "timeline": dict(sorted(timeline.items())),
        "taxi_review_list": [row for row in worklist if row["problem"] == "Taxi Complaint"][:20],
    }
    Path("report").mkdir(exist_ok=True)
    Path("report/validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "source_rows", "excluded_rows", "quality", "days_reconciled", "daily_rows_reconciled", "quarter",
    )}, indent=2))


if __name__ == "__main__":
    main()
