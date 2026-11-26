import csv
import tempfile
import unittest
from pathlib import Path

import duckdb


class BacklogTest(unittest.TestCase):
    def test_end_of_day_and_invalid_rows(self):
        sql = (Path(__file__).resolve().parents[1] / 'sql/build.sql').read_text()
        with tempfile.TemporaryDirectory() as temporary, duckdb.connect() as con:
            root = Path(temporary).as_posix()
            Path(root, 'exports').mkdir()
            snapshot = Path(root, 'tlc.csv')
            with snapshot.open('w', newline='') as file:
                csv.writer(file).writerows([
                    ['unique_key', 'agency', 'complaint_type', 'borough', 'created_date', 'closed_date', 'status', 'due_date'],
                    ['1', 'TLC', 'Taxi Complaint', 'QUEENS', '2024-12-31', '2025-01-01', 'Closed', ''],
                    ['2', 'TLC', 'Taxi Complaint', 'QUEENS', '2025-01-01', '2025-01-01', 'Closed', ''],
                    ['3', 'TLC', '', 'QUEENS', '2025-01-01', '', 'Closed', ''],
                    ['4', 'TLC', 'Taxi Complaint', 'QUEENS', '2025-01-01', '2025-01-02', 'Closed', ''],
                    ['5', 'TLC', 'Taxi Complaint', '', '2025-01-01', '2024-12-31', 'Closed', ''],
                ])
            con.execute('SET VARIABLE snapshot_file = ?', [snapshot.as_posix()])
            con.execute('SET VARIABLE export_dir = ?', [f'{root}/exports'])
            con.execute(sql)
            days = con.execute('''
                SELECT sum(arrivals), sum(closures), sum(backlog), sum(aged30)
                FROM daily GROUP BY day ORDER BY day LIMIT 2
            ''').fetchall()
            self.assertEqual(days, [(3, 2, 2, 0), (0, 1, 1, 0)])
            self.assertEqual(con.execute('SELECT reason FROM excluded_requests').fetchall(), [('Closure before creation',)])
            self.assertEqual(con.execute("SELECT problem FROM requests WHERE unique_key = '3'").fetchone(), ('Unknown',))
            aged = con.execute("SELECT sum(aged30) FROM daily WHERE day = '2025-01-31'").fetchone()[0]
            self.assertEqual(aged, 1)


if __name__ == '__main__':
    unittest.main()
