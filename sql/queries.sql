-- queries.sql — useful manufacturing queries for oee-production-line-monitor
-- Run against the SQLite database built by sql/build_db.py:
--   sqlite3 outputs/manufacturing.db < sql/queries.sql
-- Every query below was verified against the sample database (see README).

-- 1. Yield by line and shift (good units / units produced)
SELECT
    l.line_name,
    s.shift_name,
    SUM(r.units_produced) AS units_produced,
    SUM(r.good_units) AS good_units,
    ROUND(100.0 * SUM(r.good_units) / SUM(r.units_produced), 2) AS yield_pct
FROM production_runs r
JOIN lines l  ON l.line_id = r.line_id
JOIN shifts s ON s.shift_id = r.shift_id
GROUP BY l.line_name, s.shift_name
ORDER BY yield_pct ASC;

-- 2. Top defect codes (total defective units per code)
SELECT
    defect_code,
    SUM(defect_count) AS defective_units
FROM defects
GROUP BY defect_code
ORDER BY defective_units DESC;

-- 3. Downtime minutes by reason (Pareto order)
SELECT
    reason,
    SUM(minutes) AS downtime_minutes,
    COUNT(*) AS events
FROM downtime_events
GROUP BY reason
ORDER BY downtime_minutes DESC;

-- 4. OEE inputs by day: availability, performance, quality, OEE
--    Availability = operating / planned
--    Performance  = (ideal cycle * units) / operating seconds, capped at 1.0
--    Quality      = good / produced
--    Ratios are computed from the day's summed inputs (volume-weighted),
--    not averaged from per-run percentages.
SELECT
    r.run_date AS day,
    ROUND(1.0 * SUM(r.planned_minutes - r.downtime_minutes) / SUM(r.planned_minutes), 4) AS availability,
    ROUND(MIN(1.0, SUM(l.ideal_cycle_seconds * r.units_produced) / (SUM(r.planned_minutes - r.downtime_minutes) * 60.0)), 4) AS performance,
    ROUND(1.0 * SUM(r.good_units) / SUM(r.units_produced), 4) AS quality,
    ROUND(
        (1.0 * SUM(r.planned_minutes - r.downtime_minutes) / SUM(r.planned_minutes))
        * MIN(1.0, SUM(l.ideal_cycle_seconds * r.units_produced) / (SUM(r.planned_minutes - r.downtime_minutes) * 60.0))
        * (1.0 * SUM(r.good_units) / SUM(r.units_produced)), 4
    ) AS oee
FROM production_runs r
JOIN lines l ON l.line_id = r.line_id
GROUP BY r.run_date
ORDER BY r.run_date;

-- 5. Worst-performing shifts (lowest OEE, bottom 10)
SELECT
    r.run_date AS day,
    l.line_name,
    s.shift_name,
    ROUND(
        (1.0 * (r.planned_minutes - r.downtime_minutes) / r.planned_minutes)
        * MIN(1.0, (l.ideal_cycle_seconds * r.units_produced) / ((r.planned_minutes - r.downtime_minutes) * 60.0))
        * (1.0 * r.good_units / r.units_produced), 4
    ) AS oee,
    r.downtime_minutes
FROM production_runs r
JOIN lines l  ON l.line_id = r.line_id
JOIN shifts s ON s.shift_id = r.shift_id
ORDER BY oee ASC
LIMIT 10;

-- 6. Defect rate trend by week (defective units per 1,000 produced)
SELECT
    strftime('%Y-W%W', r.run_date) AS week,
    SUM(r.units_produced) AS units_produced,
    SUM(r.units_produced - r.good_units) AS defective_units,
    ROUND(1000.0 * SUM(r.units_produced - r.good_units) / SUM(r.units_produced), 2) AS defects_per_1000
FROM production_runs r
GROUP BY week
ORDER BY week;

-- 7. Total units and downtime by line (quick line comparison)
SELECT
    l.line_name,
    SUM(r.units_produced) AS units_produced,
    SUM(r.downtime_minutes) AS downtime_minutes,
    ROUND(100.0 * SUM(r.downtime_minutes) / SUM(r.planned_minutes), 2) AS downtime_pct_of_planned
FROM production_runs r
JOIN lines l ON l.line_id = r.line_id
GROUP BY l.line_name
ORDER BY downtime_pct_of_planned DESC;
