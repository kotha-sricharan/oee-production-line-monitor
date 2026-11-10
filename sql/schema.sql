-- schema.sql — manufacturing database for oee-production-line-monitor
-- SQLite. Load with:  sqlite3 manufacturing.db < sql/schema.sql
-- Or use sql/build_db.py, which creates the schema and loads the sample CSVs.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS lines (
    line_id               TEXT PRIMARY KEY,
    line_name             TEXT NOT NULL,
    ideal_cycle_seconds   REAL NOT NULL CHECK (ideal_cycle_seconds > 0),
    location              TEXT
);

CREATE TABLE IF NOT EXISTS shifts (
    shift_id    INTEGER PRIMARY KEY,
    shift_name  TEXT NOT NULL UNIQUE,   -- Day / Swing / Night
    start_time  TEXT NOT NULL,          -- HH:MM, 24-hour clock
    end_time    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS production_runs (
    run_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date          TEXT NOT NULL,    -- YYYY-MM-DD
    line_id           TEXT NOT NULL REFERENCES lines (line_id),
    shift_id          INTEGER NOT NULL REFERENCES shifts (shift_id),
    planned_minutes   INTEGER NOT NULL CHECK (planned_minutes > 0),
    downtime_minutes  INTEGER NOT NULL DEFAULT 0 CHECK (downtime_minutes >= 0),
    units_produced    INTEGER NOT NULL CHECK (units_produced >= 0),
    good_units        INTEGER NOT NULL CHECK (good_units >= 0),
    CHECK (good_units <= units_produced),
    CHECK (downtime_minutes <= planned_minutes),
    UNIQUE (run_date, line_id, shift_id)
);

CREATE TABLE IF NOT EXISTS defects (
    defect_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER NOT NULL REFERENCES production_runs (run_id),
    defect_code  TEXT NOT NULL,         -- e.g. D01 cosmetic, D02 dimensional
    defect_count INTEGER NOT NULL CHECK (defect_count > 0)
);

CREATE TABLE IF NOT EXISTS downtime_events (
    event_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    INTEGER NOT NULL REFERENCES production_runs (run_id),
    reason    TEXT NOT NULL,            -- operator-entered reason, e.g. Changeover
    minutes   INTEGER NOT NULL CHECK (minutes > 0)
);

CREATE INDEX IF NOT EXISTS idx_runs_date_line ON production_runs (run_date, line_id);
CREATE INDEX IF NOT EXISTS idx_downtime_reason ON downtime_events (reason);
CREATE INDEX IF NOT EXISTS idx_defects_code ON defects (defect_code);
