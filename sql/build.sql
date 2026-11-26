CREATE OR REPLACE TABLE staged_requests AS
SELECT unique_key, nullif(trim(complaint_type), '') AS problem,
       nullif(trim(borough), '') AS borough,
       try_cast(created_date AS timestamp) AS opened,
       try_cast(closed_date AS timestamp) AS closed,
       closed_date, status, due_date
FROM read_csv(getvariable('snapshot_file'), all_varchar = true);

CREATE OR REPLACE TABLE excluded_requests AS
SELECT unique_key, CASE
    WHEN opened IS NULL THEN 'Missing or invalid creation'
    WHEN closed IS NULL THEN 'Invalid closure'
    ELSE 'Closure before creation'
  END AS reason
FROM staged_requests
WHERE opened IS NULL OR (closed_date IS NOT NULL AND closed IS NULL) OR closed < opened;

CREATE OR REPLACE TABLE requests AS
SELECT unique_key, coalesce(problem, 'Unknown') AS problem,
       coalesce(borough, 'Unknown') AS borough, opened, closed
FROM staged_requests ANTI JOIN excluded_requests USING (unique_key);

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
TO (getvariable('export_dir') || '/daily.csv') (HEADER);

COPY (
  SELECT unique_key, problem, borough, opened::DATE AS created_day,
         DATE '2025-03-31' - opened::DATE AS age_days
  FROM requests
  WHERE opened < TIMESTAMP '2025-04-01'
    AND (closed IS NULL OR closed >= TIMESTAMP '2025-04-01')
  ORDER BY age_days DESC, unique_key
) TO (getvariable('export_dir') || '/open_march31.csv') (HEADER);
