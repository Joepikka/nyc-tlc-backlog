from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

exports = Path("exports").resolve()
exports.mkdir(exist_ok=True)
with TemporaryDirectory(dir=exports, prefix=".build-") as staging, duckdb.connect("data/tlc.duckdb") as con:
    con.execute("SET VARIABLE snapshot_file = ?", [str(Path("data/tlc.csv").resolve())])
    con.execute("SET VARIABLE export_dir = ?", [Path(staging).as_posix()])
    con.execute("BEGIN")
    con.execute(Path("sql/build.sql").read_text())
    con.execute("COMMIT")
    for filename in ("daily.csv", "open_march31.csv"):
        Path(staging, filename).replace(exports / filename)
    print("Q1 arrivals and closures:", con.execute("SELECT sum(arrivals), sum(closures) FROM daily").fetchone())
    print("March 31 backlog:", con.execute("SELECT sum(backlog) FROM daily WHERE day = DATE '2025-03-31'").fetchone()[0])
