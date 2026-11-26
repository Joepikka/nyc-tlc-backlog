import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

base = "https://data.cityofnewyork.us/resource/erm2-nwe9"
where = ("agency='TLC' AND created_date >= '2024-01-01' "
         "AND created_date < '2025-04-01' AND (created_date >= '2025-01-01' "
         "OR closed_date IS NULL OR closed_date >= '2025-01-01')")
fields = "unique_key,agency,complaint_type,borough,created_date,closed_date,status,due_date"
query = {"$where": where, "$select": fields, "$order": "unique_key", "$limit": 50000}
response = requests.get(base + ".csv", params=query, timeout=90)
response.raise_for_status()
rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
count = requests.get(base + ".json", params={"$where": where, "$select": "count(*) AS n"}, timeout=90)
count.raise_for_status()
assert 0 < len(rows) == int(count.json()[0]["n"]) < 50000
assert len({r["unique_key"] for r in rows}) == len(rows)
Path("data/tlc.csv").write_bytes(response.content)
manifest = {"url": response.url, "rows": len(rows), "utc": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(response.content).hexdigest()}
Path("data/manifest.json").write_text(json.dumps(manifest, indent=2))
print(manifest)
