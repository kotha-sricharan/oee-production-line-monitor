# OEE Production Line Monitor

A Python CLI tool + SQL pack for day-to-day production-line monitoring:
load shift logs, compute **OEE (Availability × Performance × Quality)**
per line / shift / day, chart the downtime Pareto, and write a
shift-handover report. A companion SQLite pack stores the same data
relationally and answers the yield / defect / downtime questions a
production team asks every morning.

**Author:** Sri Charan Kotha

> **All sample data in this repo is synthetic** — invented for
> demonstration only. It does not come from Tesla or any real production
> line, and nothing here claims Tesla experience.

## Why this project

It maps directly to the work of a production-line role (e.g. Tesla NCM
Process Technician, Buffalo NY, Req 259251):

| Job requirement | How this project covers it |
|---|---|
| Day-to-day coverage of the production line | OEE computed per line / shift / day from shift logs, so any out-of-control shift is visible immediately |
| Rapid response on out-of-control processes | The handover report flags the latest day's weakest line/shift and the factor (availability / performance / quality) dragging it down |
| Root cause + countermeasures to improve yield | Downtime Pareto ranks loss reasons; the report turns the top loss into a recommended action for the incoming shift |
| Summarize and analyze yield and process data | `oee_summary.csv` + SQL yield/defect-trend queries aggregate the same data two ways (pandas and SQL) |
| Work with production control on inventory | `production_runs` records units produced vs. good units per shift — the exact inputs production control needs to disposition inventory |
| Use Tableau + SQL to manage, synthesize and interpret data | SQL pack (`schema.sql`, `queries.sql`) does the Tableau-style aggregation in SQL; the Pareto PNG is the same chart a Tableau dashboard would show |
| Support Lean / continuous improvement / 5S | Pareto + OEE trend make the biggest losses visible so improvement work targets the right reason first |

## What it does

### 1. CLI tool — `src/oee_monitor.py`

```bash
pip install -r requirements.txt
python src/oee_monitor.py --input data/shift_logs.csv --out outputs/
```

Given a shift-log CSV with columns `date, line, shift, planned_minutes,
downtime_minutes, downtime_reason, units_produced, ideal_cycle_seconds,
good_units`, it produces:

- **`oee_summary.csv`** — Availability, Performance, Quality and OEE for
  every line / shift / day.
- **`downtime_pareto.png`** — bar chart of downtime minutes by reason
  with a cumulative-% line and the 80% mark.
- **`handover_report.md`** — latest-day OEE table, top-5 losses, and a
  recommended action per line/shift for the incoming crew.

OEE definitions (standard):

- Availability = (planned − downtime) / planned
- Performance = (ideal cycle seconds × units produced) / (operating minutes × 60), capped at 100%
- Quality = good units / units produced
- **OEE = Availability × Performance × Quality**

### 2. SQL pack — `sql/`

```bash
python sql/build_db.py --csv data/shift_logs.csv --db outputs/manufacturing.db
sqlite3 outputs/manufacturing.db < sql/queries.sql
```

- **`schema.sql`** — `lines`, `shifts`, `production_runs`, `defects`,
  `downtime_events` (with foreign keys, checks and indexes).
- **`build_db.py`** — creates the database from the schema and loads the
  sample CSVs into it (168 production runs, 124 downtime events).
- **`queries.sql`** — 7 verified queries:
  1. Yield by line and shift
  2. Top defect codes
  3. Downtime minutes by reason (Pareto order)
  4. OEE inputs by day (availability / performance / quality / OEE)
  5. Worst-performing shifts (bottom 10 by OEE)
  6. Defect-rate trend by week (defects per 1,000 units)
  7. Total units and downtime by line

## Sample output (from the shipped synthetic data)

2 lines (NCM-1, NCM-2) × 4 weeks × 3 shifts = **168 shift rows**,
2026-10-12 to 2026-11-08.

```
Rows loaded:            168
Overall OEE:            77.9%
Overall Availability:   93.6%
Overall Performance:    85.1%
Overall Quality:        97.9%
Total downtime:         5182 minutes
Top downtime reasons:
  - Machine Breakdown: 2012 min (38.8%)
  - Changeover: 1207 min (23.3%)
  - Quality Hold: 499 min (9.6%)
```

SQL spot checks on the same data: worst shift was NCM-2 Swing on
2026-10-12 (OEE 61.6%, 105 downtime minutes); weekly defect rate runs
18.3–22.9 defects per 1,000 units; NCM-1 produced 43,495 units with
7.0% of planned time lost to downtime.

## Project layout

```
oee-production-line-monitor/
├── README.md
├── requirements.txt
├── LICENSE
├── data/
│   └── shift_logs.csv          # synthetic sample data (clearly labeled)
├── src/
│   └── oee_monitor.py          # CLI: OEE, Pareto chart, handover report
├── sql/
│   ├── schema.sql              # manufacturing DB schema
│   ├── queries.sql             # 7 verified queries
│   └── build_db.py             # builds SQLite DB from the sample CSVs
└── outputs/                    # generated: oee_summary.csv, downtime_pareto.png,
    └── ...                     #   handover_report.md (manufacturing.db is
                                #   rebuilt locally by build_db.py; *.db is gitignored)
```

## Requirements

- Python 3.10+ (developed on 3.12)
- pandas, numpy, matplotlib (see `requirements.txt`)
- `sqlite3` CLI is optional — `build_db.py` uses Python's built-in `sqlite3`

## License

MIT — see `LICENSE`.
