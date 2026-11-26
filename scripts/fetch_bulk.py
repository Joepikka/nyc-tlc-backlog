"""Download NYC 311 citywide records by creation month and derive the TLC cohort."""

import csv
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://data.cityofnewyork.us/resource/erm2-nwe9"
START = date(2024, 1, 1)
STOP = date(2025, 4, 1)
LIMIT = 500_000
FIELDS = ("unique_key", "agency", "complaint_type", "borough", "created_date",
          "closed_date", "status", "due_date")
RAW = Path("data/citywide")


def next_month(day):
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def session():
    client = requests.Session()
    client.mount("https://", HTTPAdapter(max_retries=Retry(
        total=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504],
    )))
    return client


def download(month, expected):
    name = month.strftime("%Y-%m")
    path = RAW / f"{name}.csv"
    part = path.with_suffix(".csv.part")
    metadata = path.with_suffix(".json")
    if metadata.exists() and path.exists():
        info = json.loads(metadata.read_text())
        if info["rows"] == expected and info["bytes"] == path.stat().st_size:
            with path.open("rb") as file:
                if hashlib.file_digest(file, "sha256").hexdigest() == info["sha256"]:
                    info["fetched_utc"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
                    print(f"{name}: cached {expected:,} rows", flush=True)
                    return info

    end = next_month(month)
    where = f"created_date >= '{month}' AND created_date < '{end}'"
    with session() as client, client.get(BASE + ".csv", params={
        "$where": where, "$order": "created_date,unique_key", "$limit": LIMIT,
    }, stream=True, timeout=(20, 120)) as response:
        response.raise_for_status()
        digest = hashlib.sha256()
        with part.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                file.write(chunk)
                digest.update(chunk)
        url = response.url

    with duckdb.connect() as con:
        rows, distinct_keys = con.execute(
            "SELECT count(*), count(DISTINCT unique_key) FROM read_csv(?, all_varchar = true)",
            [str(part)],
        ).fetchone()
    if not (0 < rows == distinct_keys == expected < LIMIT):
        raise ValueError(f"{name}: expected {expected:,} unique records, got {rows:,} rows / {distinct_keys:,} keys")

    part.replace(path)
    info = {"month": name, "rows": rows, "bytes": path.stat().st_size, "sha256": digest.hexdigest(), "url": url,
            "fetched_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()}
    metadata.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(f"{name}: {rows:,} rows, {info['bytes'] / 1_000_000:.1f} MB", flush=True)
    return info


def main():
    RAW.mkdir(exist_ok=True, parents=True)
    with session() as client:
        response = client.get(BASE + ".json", params={
            "$where": f"created_date >= '{START}' AND created_date < '{STOP}'",
            "$select": "date_trunc_ym(created_date) AS month, count(*) AS n",
            "$group": "month",
        }, timeout=120)
        response.raise_for_status()
        expected = {item["month"][:7]: int(item["n"]) for item in response.json()}
    months = []
    month = START
    while month < STOP:
        months.append(month)
        month = next_month(month)

    with ThreadPoolExecutor(max_workers=5) as pool:
        partitions = list(pool.map(download, months, [expected[month.strftime("%Y-%m")] for month in months]))

    paths = [str(RAW / f"{item['month']}.csv") for item in partitions]
    with duckdb.connect() as con:
        con.execute("SET threads = 4")
        con.execute("SET memory_limit = '2GB'")
        source = con.read_csv(paths, all_varchar=True, union_by_name=True)
        source.create_view("citywide")
        rows, keys, agencies = con.execute(
            "SELECT count(*), count(DISTINCT unique_key), count(DISTINCT agency) FROM citywide"
        ).fetchall()[0]
        if not rows == keys == sum(expected.values()):
            raise ValueError(f"Citywide counts mismatch: {rows} rows, {keys} keys, {sum(expected.values())} expected")
        cohort = con.sql(f"""
            SELECT {', '.join(FIELDS)}
            FROM citywide
            WHERE agency = 'TLC' AND (created_date >= '2025-01-01'
                 OR nullif(closed_date, '') IS NULL OR closed_date >= '2025-01-01')
            ORDER BY unique_key
        """).fetchall()
    keys = {row[0] for row in cohort}
    if len(keys) != len(cohort) or None in keys or not keys:
        raise ValueError("TLC cohort must have one row per nonblank request key")

    path = Path("data/tlc.csv")
    staging = path.with_suffix(".csv.part")
    with staging.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(cohort)
    snapshot_hash = hashlib.sha256(staging.read_bytes()).hexdigest()
    staging.replace(path)
    timestamp = datetime.now(timezone.utc).isoformat()
    manifest = {"url": BASE, "rows": len(cohort), "utc": timestamp, "sha256": snapshot_hash,
                "citywide_manifest": "data/citywide-manifest.json"}
    Path("data/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    citywide = {"url": BASE, "utc": timestamp, "created_from_inclusive": START.isoformat(),
                "created_to_exclusive": STOP.isoformat(), "rows": rows, "agencies": agencies,
                "bytes": sum(item["bytes"] for item in partitions), "partitions": partitions}
    Path("data/citywide-manifest.json").write_text(json.dumps(citywide, indent=2) + "\n", encoding="utf-8")
    print(f"Scanned {rows:,} citywide requests across {agencies} agencies "
          f"({citywide['bytes'] / 1_000_000_000:.2f} GB); selected {len(cohort):,} TLC rows.", flush=True)


if __name__ == "__main__":
    main()
