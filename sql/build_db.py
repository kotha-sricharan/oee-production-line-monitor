#!/usr/bin/env python3
"""build_db.py — build the manufacturing SQLite database from sample data.

Creates the schema in sql/schema.sql, then loads data/shift_logs.csv
(synthetic sample data) into production_runs, downtime_events and defects.

Usage:
    python sql/build_db.py [--csv data/shift_logs.csv] [--db outputs/manufacturing.db]

Re-running deletes the existing database file first, so the build is
repeatable. Defect codes are assigned deterministically from the sample
rows for demonstration; in a real deployment they would come from the
quality system.
"""

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent

SHIFTS = [
    (1, "Day", "06:00", "14:00"),
    (2, "Swing", "14:00", "22:00"),
    (3, "Night", "22:00", "06:00"),
]

# Synthetic defect-code split used only for the sample data.
DEFECT_CODES = ["D01-cosmetic", "D02-dimensional", "D03-contamination", "D04-electrical"]


def load_csv_rows(csv_path: Path) -> list[dict]:
    """Read the shift-log CSV, skipping '#' comment lines (synthetic banner)."""
    with csv_path.open(newline="", encoding="utf-8") as f:
        lines = [ln for ln in f if not ln.startswith("#")]
    reader = csv.DictReader(lines)
    rows = []
    for row in reader:
        rows.append(
            {
                "date": row["date"],
                "line": row["line"],
                "shift": row["shift"],
                "planned_minutes": int(row["planned_minutes"]),
                "downtime_minutes": int(row["downtime_minutes"]),
                "downtime_reason": row["downtime_reason"].strip(),
                "units_produced": int(row["units_produced"]),
                "ideal_cycle_seconds": float(row["ideal_cycle_seconds"]),
                "good_units": int(row["good_units"]),
            }
        )
    return rows


def build(csv_path: Path, db_path: Path) -> dict:
    schema = (HERE / "schema.sql").read_text(encoding="utf-8")
    rows = load_csv_rows(csv_path)

    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema)
        conn.execute("PRAGMA foreign_keys = ON")

        for line_id in sorted({r["line"] for r in rows}):
            cycle = next(
                r["ideal_cycle_seconds"] for r in rows if r["line"] == line_id
            )
            conn.execute(
                "INSERT INTO lines (line_id, line_name, ideal_cycle_seconds, location)"
                " VALUES (?, ?, ?, ?)",
                (line_id, line_id, cycle, "Buffalo, NY"),
            )
        conn.executemany(
            "INSERT INTO shifts (shift_id, shift_name, start_time, end_time)"
            " VALUES (?, ?, ?, ?)",
            SHIFTS,
        )
        shift_ids = {name: sid for sid, name, _, _ in SHIFTS}

        runs = downtime = defects = 0
        for i, r in enumerate(rows):
            cur = conn.execute(
                "INSERT INTO production_runs"
                " (run_date, line_id, shift_id, planned_minutes,"
                "  downtime_minutes, units_produced, good_units)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    r["date"],
                    r["line"],
                    shift_ids[r["shift"]],
                    r["planned_minutes"],
                    r["downtime_minutes"],
                    r["units_produced"],
                    r["good_units"],
                ),
            )
            run_id = cur.lastrowid
            runs += 1
            if r["downtime_minutes"] > 0 and r["downtime_reason"]:
                conn.execute(
                    "INSERT INTO downtime_events (run_id, reason, minutes)"
                    " VALUES (?, ?, ?)",
                    (run_id, r["downtime_reason"], r["downtime_minutes"]),
                )
                downtime += 1
            defective = r["units_produced"] - r["good_units"]
            if defective > 0:
                conn.execute(
                    "INSERT INTO defects (run_id, defect_code, defect_count)"
                    " VALUES (?, ?, ?)",
                    (run_id, DEFECT_CODES[i % len(DEFECT_CODES)], defective),
                )
                defects += 1
        conn.commit()
    finally:
        conn.close()

    return {"runs": runs, "downtime_events": downtime, "defect_rows": defects}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build manufacturing SQLite DB")
    parser.add_argument(
        "--csv", default=str(PROJECT_ROOT / "data" / "shift_logs.csv")
    )
    parser.add_argument(
        "--db", default=str(PROJECT_ROOT / "outputs" / "manufacturing.db")
    )
    args = parser.parse_args(argv)

    stats = build(Path(args.csv), Path(args.db))
    print(f"Database built: {args.db}")
    print(f"  production_runs:  {stats['runs']}")
    print(f"  downtime_events:  {stats['downtime_events']}")
    print(f"  defect rows:      {stats['defect_rows']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
