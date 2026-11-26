# Project 1 · Which service requests should a supervisor review?

**Build a Power BI operations report and a spreadsheet worklist for a morning supervisor.** Use actual New York City 311 requests handled by the Taxi and Limousine Commission (TLC). At the end of any reporting day, the supervisor should be able to see which queue is growing, whether its older cases are accumulating, and which records deserve manual review. This is a retrospective simulation of that decision.

**Why build this first.** Your retail and vegetable-price projects already show large datasets and trends. This adds something an interviewer can verify quickly. You define an operational KPI, reconstruct it from dates, reconcile it against independent counts, and deliver a usable worklist. Amazon’s India BI internship calls for SQL, Excel, recurring reporting, validation and communicating recommendations. EY’s experienced Kochi analyst role illustrates how teams use Power Query, DAX and operational metrics. These are reasons to showcase the skills, independent of the employers’ location or seniority requirements. [Amazon BIE internship](https://www.amazon.jobs/en/jobs/10498165/business-intelligence-engineer-intern-2027) · [EY Kochi role](https://careers.ey.com/ey/job/Kochi-Platform-Infrastructure-Data-Analyst-KL-682313/1447576333/)

## Choose the data and tools

| Source | Why consider it | Decision |
|---|---|---|
| **NYC 311 service requests** | Public agency records with a request key, category, creation time, recorded closure and borough. The city explains the meaning of closure. A small filtered extract supports repeatable download and day-by-day reconciliation. | **Best fit for this reporting project.** Use the official data and keep the selected dates and agency visible. [NYC dataset and dictionary](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9) · [City reporting definitions](https://www.nyc.gov/site/311reporting/faq/faq.page) |
| **UCI incident-management event log** | Genuine ServiceNow history with 141,712 events across 24,918 incidents, including state, priority and reassignment. An incident can have multiple event rows. | Prefer this source if the main question is *how often IT incidents reopen or change hands*. NYC has a simpler grain and an accessible refresh path for this decision. [UCI event log](https://archive.ics.uci.edu/dataset/498/incident%2Bmanagement%2Bprocess%2Benriched%2Bevent%2Blog) |

**Tools and cost.** Use Python + requests for extraction, DuckDB SQL for reconciliation and exports, Power BI Desktop on Windows for Power Query, modeling and DAX, and Excel for the web for the supervisor’s worklist. GitHub hosts the README and screenshots. These steps cost ₹0 in additional software or services with your existing laptop and internet. A free Microsoft account suffices for Excel web. Distribute the report as screenshots and a downloadable PBIX. That keeps access independent of Power BI Service sharing licenses. Budget **16–24 focused hours**, including testing and a portfolio walkthrough. [Power BI Desktop](https://learn.microsoft.com/en-us/power-bi/fundamentals/desktop-getting-started) · [Power BI sharing licenses](https://learn.microsoft.com/en-us/power-bi/fundamentals/end-user-license) · [Free Excel for the web](https://www.microsoft.com/en-us/microsoft-365/free-office-online-for-the-web)

## Phase A · Write the brief and set up the project

1. **Write the decision in `README.md`.** “A TLC supervisor has capacity to review 20 records. Which queue accumulated work over the quarter, and which of its oldest open records should the supervisor inspect first?” Twenty is an illustrative review capacity. The output supports administrative review. Age alone cannot establish safety urgency, blame or staffing requirements.
2. **Pin the coverage.** Report **January 1 through March 31, 2025**, using requests created **from January 1, 2024 onward**. Include earlier-in-cohort requests still open when Q1 began. The dashboard title should say *NYC TLC · Q1 2025 · requests created since Jan 2024*. Earlier requests fall outside the analysis. NYC split the pre-2020 archive and updated display labels. The API still exposes `complaint_type` for the field displayed as Problem. [Official dataset updates](https://www.nyc.gov/opendata/news/all-news/311-Service-Requests-Updates)
3. **Create the folders and environment.** Run from PowerShell, with Python 3 installed. Put the scripts below in the named files. Run all commands from the new project root.

   ```powershell
   mkdir service-request-backlog
   cd service-request-backlog
   mkdir data, sql, scripts, exports, report
   py -3 -m venv .venv
   .\.venv\Scripts\python -m pip install requests duckdb
   .\.venv\Scripts\python -m pip freeze > requirements.txt
   ```

## Phase B · Take a reproducible snapshot

1. **Download the narrow slice.** Save this as `scripts/fetch.py` and run `.\.venv\Scripts\python scripts/fetch.py`. It requests only fields used in the analysis, checks for silent truncation, and saves a manifest. If the city revises historical records, save the new snapshot in a fresh project copy before comparing versions. The extract used while researching this guide was about 1.9 MB.

   ```python
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
   ```

2. **Inspect five records and the schema.** One row represents one request. Keep the key as text and use city-local timestamps. Use `created_date` and `closed_date` to reconstruct history. The current `status` is useful for quality checks. Check duplicates, missing creation time, closure before creation, missing borough/category, and current “Closed” with no closure timestamp. Flag conflicting records and record their count before excluding them. Give missing categories a visible “Unknown” group so totals still reconcile.
3. **Define the metrics on paper.** “Open at end of day D” means created before the following local midnight and closed at or after that midnight, or lacking a recorded closure. “Closed on D” counts recorded closures on D, including requests created earlier. “Age” is calendar dates elapsed since creation. “Aged 30+” is a project review threshold. NYC cautions that recorded closure can mean an agency saw or began action on a request. A missing closure date can overstate outstanding work. The checked extract had **zero populated due dates**. Use age bands and recorded closure for this version. [NYC definitions](https://www.nyc.gov/site/311reporting/faq/faq.page)

## Phase C · Build the SQL model and worklist

1. **Save the model below in `sql/build.sql`.** It creates a calendar and a daily table with one row per date, problem and borough. Each request contributes to arrivals and recorded closures once. It contributes to the open balance on every day it remains open. Crossing 90 dates with this small extract is inexpensive and makes the rules auditable.

   ```sql
   CREATE OR REPLACE TABLE requests AS
   SELECT unique_key, coalesce(nullif(trim(complaint_type), ''), 'Unknown') AS problem,
          coalesce(nullif(trim(borough), ''), 'Unknown') AS borough,
          created_date::TIMESTAMP AS opened, closed_date::TIMESTAMP AS closed
   FROM read_csv('data/tlc.csv', all_varchar = true);

   CREATE OR REPLACE TABLE daily AS
   WITH calendar AS (
     SELECT d::DATE AS day FROM generate_series(
       DATE '2025-01-01', DATE '2025-03-31', INTERVAL 1 DAY) AS dates(d)
   ), states AS (
     SELECT day, problem, borough, opened, closed,
            opened < day + INTERVAL 1 DAY AND
            (closed IS NULL OR closed >= day + INTERVAL 1 DAY) AS is_open
     FROM calendar CROSS JOIN requests
   )
   SELECT day, problem, borough,
          count(*) FILTER (WHERE opened::DATE = day) AS arrivals,
          count(*) FILTER (WHERE closed::DATE = day) AS closures,
          count(*) FILTER (WHERE is_open) AS backlog,
          count(*) FILTER (WHERE is_open AND day - opened::DATE >= 30) AS aged30
   FROM states GROUP BY day, problem, borough;

   COPY (SELECT * FROM daily ORDER BY day, problem, borough)
   TO 'exports/daily.csv' (HEADER);

   COPY (
     SELECT unique_key, problem, borough, opened::DATE AS created_day,
            DATE '2025-03-31' - opened::DATE AS age_days
     FROM requests
     WHERE opened < TIMESTAMP '2025-04-01'
       AND (closed IS NULL OR closed >= TIMESTAMP '2025-04-01')
     ORDER BY age_days DESC, unique_key
   ) TO 'exports/open_march31.csv' (HEADER);
   ```

2. **Run it locally.** Save the following as `scripts/build.py`, then run `.\.venv\Scripts\python scripts/build.py`. To repeat, keep the same input snapshot and run the build again.

   ```python
   from pathlib import Path
   import duckdb

   with duckdb.connect("data/tlc.duckdb") as con:
       con.execute(Path("sql/build.sql").read_text())
       print("Q1 arrivals and closures:", con.execute("SELECT sum(arrivals), sum(closures) FROM daily").fetchone())
       print("March 31 backlog:", con.execute("SELECT sum(backlog) FROM daily WHERE day = DATE '2025-03-31'").fetchone()[0])
   ```

3. **Create the prioritized worklist.** Open `open_march31.csv` in Excel for the web, filter the problem to *Taxi Complaint*, sort by age descending and key ascending, and keep the first 20 records. Save as `report/review-list.xlsx`. Include a header with the simulated review date, scope and ordering rule. Add editable columns for reviewer, action and follow-up date. Keep the full export so the supervisor can choose another category. Use only columns known at the review cutoff. For a different day, substitute the reporting date and its following midnight together.
4. **Check the logic against four toy records.** A request created Dec 31 and closed Jan 1 contributes to opening balance and Jan 1 closures. One created and closed on Jan 1 contributes to both flows and zero end-of-day backlog. One created Jan 1 with no closure stays open. One created Jan 1 and closed exactly at Jan 2 midnight is open at Jan 1 end and closes Jan 2. With one of each, expect opening balance 1, Jan 1 arrivals 3, closures 2, end balance 2. This catches the common off-by-one error.

## Phase D · Reconcile the numbers before making visuals

1. **Run an independent check directly against `requests`.** Count carry-in using `opened < '2025-01-01' AND (closed IS NULL OR closed >= '2025-01-01')`. Add quarter arrivals and subtract quarter closures using the half-open interval [Jan 1, Apr 1). Compare with a direct end-of-quarter count. Repeat for each of the 90 days. For every day, starting balance + arrivals − closures must equal ending balance. Test one filtered borough and one category as well as the total.
2. **Compare with the research snapshot.** These are checkpoints from the official extract checked **18 November 2026**. If a future pull differs, compare the source count, filter, checksum and timestamp, then document the difference. Keep separate records for data revisions and code errors. [Official source](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9)

   | Check | Expected on checked snapshot |
   |---|---:|
   | Unique requests in the extract | 17,341 |
   | Opening balance before Jan 1 | 9,335 |
   | Q1 arrivals | 8,006 |
   | Q1 recorded closures | 7,656 |
   | March 31 ending balance | 9,685 |

   The checked CSV's SHA-256 was `a73d400e1f7b897f213feb10d088f7ba30084ac95e3d6c9d9126ae17c4d0236d`. For a quick Excel cross-check, filtering the full ending worklist to *Taxi Complaint* should return **2,089** rows before you take the oldest 20.

3. **Find the actionable result.** Group by problem. Calculate quarter arrivals, quarter closures and net change. The checked data show **4,351** arrivals for *For Hire Vehicle Complaint* while its backlog **fell by 389**. *Taxi Complaint* had **1,757** arrivals while its backlog **grew by 412**. A defensible recommendation is to review the oldest taxi complaints and ask which step is slowing recorded closure. Staff capacity and root cause require internal operational evidence. [NYC request data](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9)

## Phase E · Build the Power BI report

1. **Load with Power Query.** In Desktop use Home → Get data → Text/CSV → `exports/daily.csv` → Transform Data. Set day to Date, geography and problem to Text, and counts to Whole Number. Rename the query `Daily`. Make a text parameter for the export folder so another person can refresh the PBIX. Load the March worklist as a separate detail table with a visible fixed March 31 label. Keep the daily date slicer off the fixed-date worklist.
2. **Build relationships.** Add a date table using the DAX below. Mark it as the date table and relate `Dates[Date]` one-to-many to `Daily[day]`. If both report pages use problem and borough slicers, make distinct Problem and Borough lookup tables from `Daily` in Power Query and relate each to both fact tables with single-direction filters. Check that each lookup key is unique. [Microsoft’s Power BI modeling guidance](https://learn.microsoft.com/en-us/power-bi/guidance/star-schema)

   ```dax
   Dates = CALENDAR(DATE(2025,1,1), DATE(2025,3,31))
   ```

3. **Add these measures one at a time.** Arrivals and closures can be added over time. A backlog card shows the last selected day’s balance. Summing 90 backlog balances would give case-days. Compare the March 31 card with SQL before styling the report.

   ```dax
   Arrivals = SUM(Daily[arrivals])
   ```
   ```dax
   Closures = SUM(Daily[closures])
   ```
   ```dax
   Net change = [Arrivals] - [Closures]
   ```
   ```dax
   Closing backlog =
   VAR LastDay = MAX('Dates'[Date])
   RETURN CALCULATE(SUM(Daily[backlog]), 'Dates'[Date] = LastDay)
   ```
   ```dax
   Aged 30+ share =
   VAR LastDay = MAX('Dates'[Date])
   VAR Older = CALCULATE(SUM(Daily[aged30]), 'Dates'[Date] = LastDay)
   RETURN DIVIDE(Older, [Closing backlog])
   ```

4. **Lay out two pages.** On *Queue health*, show closing backlog, net change and aged share across the top, a daily backlog line underneath, and a ranked horizontal bar of net change by problem. Sort the bar so growing queues are easy to find and mark zero. Put dates and cohort scope in the subtitle. On *Review list · March 31*, show category, key, borough, creation date and age. Add a problem slicer. Verify that filtering to Taxi Complaint produces the same top records and ages as Excel.
5. **Check usability.** Set March 31 alone, then Q1, then a single borough. Confirm the closing backlog is identical for periods with the same end date and same geography. Restore all filters and confirm arrivals = 8,006 for the checked snapshot. Ask someone to identify the growing category and locate its oldest request in one minute. If they struggle, revise the labels or sorting.

## Phase F · Publish a portfolio case study

1. **Show the result upfront.** Give your README a screenshot, the 4,351 versus 1,757 finding and a one-paragraph recommendation. Link the PBIX, sample worklist, SQL, data-source manifest, metric definitions, validation results and reproduction commands. A viewer should understand the finding on a phone without installing Power BI.
2. **Record a 90-second demonstration.** Show the two categories, select the growing queue, open its worklist, then display the opening-to-closing reconciliation. Explain why a missing closure date matters. These choices demonstrate SQL, date handling, DAX, Excel and stakeholder communication in one narrative.
3. **Finish with a reproducibility check.** From a fresh project folder, follow the documented steps, set the Power Query folder parameter and refresh. Compare Q1 totals, the March 31 worklist count and the top 20 keys. Publish the result on GitHub and link it from your existing portfolio when these checks pass. GitHub’s public README suffices. If you want a standalone page, use GitHub Pages with the two screenshots and a link to the report. [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
