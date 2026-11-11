#!/usr/bin/env python3
"""OEE Production Line Monitor — CLI tool.

Loads shift-log CSVs and computes Overall Equipment Effectiveness (OEE)
per line / shift / day, builds a downtime Pareto chart, and writes a
shift-handover report in Markdown.

OEE = Availability x Performance x Quality, where:
    Availability = (planned_minutes - downtime_minutes) / planned_minutes
    Performance  = (ideal_cycle_seconds * units_produced)
                   / (operating_minutes * 60)
    Quality      = good_units / units_produced

Usage:
    python src/oee_monitor.py --input data/shift_logs.csv --out outputs/

Outputs (in --out):
    oee_summary.csv      OEE, Availability, Performance, Quality per line/shift/day
    downtime_pareto.png  Pareto chart of downtime minutes by reason
    handover_report.md   Shift-handover report with top losses and actions

The sample data shipped in data/ is synthetic, invented for demonstration.
"""

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REQUIRED_COLUMNS = [
    "date",
    "line",
    "shift",
    "planned_minutes",
    "downtime_minutes",
    "downtime_reason",
    "units_produced",
    "ideal_cycle_seconds",
    "good_units",
]


def load_shift_logs(path: Path) -> pd.DataFrame:
    """Load a shift-log CSV, skipping '#' comment lines (synthetic-data banner)."""
    df = pd.read_csv(path, comment="#", parse_dates=["date"])
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in {path}: {missing}")
    if (df["planned_minutes"] <= 0).any():
        raise ValueError("planned_minutes must be > 0 in every row")
    if (df["units_produced"] <= 0).any():
        raise ValueError("units_produced must be > 0 in every row")
    return df


def compute_oee(df: pd.DataFrame) -> pd.DataFrame:
    """Add OEE components per row and aggregate per line/shift/day.

    The grouped ratios are recomputed from the summed inputs
    (volume-weighted), not averaged from the per-row percentages:
    a high-volume shift must count more than a low-volume one.
    """
    df = df.copy()
    df["operating_minutes"] = df["planned_minutes"] - df["downtime_minutes"]
    df["availability"] = df["operating_minutes"] / df["planned_minutes"]
    df["ideal_seconds"] = df["ideal_cycle_seconds"] * df["units_produced"]
    df["performance"] = df["ideal_seconds"] / (df["operating_minutes"] * 60)
    df["performance"] = df["performance"].clip(upper=1.0)
    df["quality"] = df["good_units"] / df["units_produced"]
    df["oee"] = df["availability"] * df["performance"] * df["quality"]

    grouped = (
        df.groupby(["date", "line", "shift"], as_index=False)
        .agg(
            planned_minutes=("planned_minutes", "sum"),
            downtime_minutes=("downtime_minutes", "sum"),
            operating_minutes=("operating_minutes", "sum"),
            ideal_seconds=("ideal_seconds", "sum"),
            units_produced=("units_produced", "sum"),
            good_units=("good_units", "sum"),
        )
        .sort_values(["date", "line", "shift"])
    )
    grouped["availability"] = grouped["operating_minutes"] / grouped["planned_minutes"]
    grouped["performance"] = (
        grouped["ideal_seconds"] / (grouped["operating_minutes"] * 60)
    ).clip(upper=1.0)
    grouped["quality"] = grouped["good_units"] / grouped["units_produced"]
    grouped["oee"] = (
        grouped["availability"] * grouped["performance"] * grouped["quality"]
    )
    return df, grouped


def overall_oee(df: pd.DataFrame) -> tuple[float, float, float, float]:
    """Period-wide (availability, performance, quality, OEE).

    Recomputed from the summed inputs across the whole period, so
    shifts contribute in proportion to their production volume.
    """
    planned = df["planned_minutes"].sum()
    operating = (df["planned_minutes"] - df["downtime_minutes"]).sum()
    ideal_seconds = (df["ideal_cycle_seconds"] * df["units_produced"]).sum()
    availability = operating / planned
    performance = min(1.0, ideal_seconds / (operating * 60))
    quality = df["good_units"].sum() / df["units_produced"].sum()
    return availability, performance, quality, availability * performance * quality


def downtime_pareto(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate downtime minutes by reason, sorted worst-first, with share %."""
    pareto = (
        df[df["downtime_minutes"] > 0]
        .groupby("downtime_reason", as_index=False)["downtime_minutes"]
        .sum()
        .sort_values("downtime_minutes", ascending=False)
    )
    total = pareto["downtime_minutes"].sum()
    pareto["share_pct"] = (pareto["downtime_minutes"] / total * 100).round(1)
    pareto["cum_pct"] = pareto["share_pct"].cumsum().round(1)
    return pareto


def plot_pareto(pareto: pd.DataFrame, out_path: Path) -> None:
    """Bar chart of downtime minutes by reason with a cumulative % line."""
    fig, ax1 = plt.subplots(figsize=(10, 5.5))
    ax1.bar(pareto["downtime_reason"], pareto["downtime_minutes"], color="#1f77b4")
    ax1.set_xlabel("Downtime reason")
    ax1.set_ylabel("Downtime (minutes)")
    ax1.set_title("Downtime Pareto — minutes lost by reason")
    ax1.tick_params(axis="x", rotation=30, labelsize=9)
    for i, v in enumerate(pareto["downtime_minutes"]):
        ax1.text(i, v + 15, str(v), ha="center", fontsize=9)

    ax2 = ax1.twinx()
    ax2.plot(
        pareto["downtime_reason"],
        pareto["cum_pct"],
        color="#d62728",
        marker="o",
        linewidth=2,
    )
    ax2.set_ylabel("Cumulative % of downtime")
    ax2.set_ylim(0, 110)
    ax2.axhline(80, color="#d62728", linestyle="--", linewidth=1, alpha=0.6)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def recommended_actions(row: pd.Series, worst_reason: str) -> list[str]:
    """Rule-based actions from one line/shift's latest OEE components."""
    actions = []
    if row["availability"] < 0.85:
        actions.append(
            f"Availability {row['availability']:.1%} is the biggest drag — "
            f"top loss is {worst_reason}; review the changeover / breakdown "
            "checklist before the next shift starts."
        )
    if row["performance"] < 0.90:
        actions.append(
            f"Performance {row['performance']:.1%} is below target — check for "
            "micro-stops and reduced cycle speed, and confirm the line is "
            "running at its rated ideal cycle time."
        )
    if row["quality"] < 0.98:
        actions.append(
            f"Quality {row['quality']:.1%} is below target — hold the last "
            "production lot for inspection and log defect codes before handover."
        )
    if not actions:
        actions.append(
            "All three OEE factors are at or above target — hold the current "
            "settings and carry the run plan into the next shift."
        )
    return actions


def write_handover_report(
    df: pd.DataFrame,
    summary: pd.DataFrame,
    pareto: pd.DataFrame,
    out_path: Path,
) -> None:
    """Markdown handover report: latest-day OEE per line/shift, top losses, actions."""
    latest_date = summary["date"].max()
    latest = summary[summary["date"] == latest_date]
    worst_reason = pareto.iloc[0]["downtime_reason"] if not pareto.empty else "n/a"
    avail, perf, qual, overall = overall_oee(df)

    lines = []
    lines.append("# Shift Handover Report")
    lines.append("")
    lines.append(f"**Report date (latest shift log):** {latest_date.date()}")
    lines.append(
        f"**Coverage:** {summary['date'].nunique()} days, "
        f"{', '.join(sorted(summary['line'].unique()))}, "
        "Day / Swing / Night shifts"
    )
    lines.append(
        f"**Overall OEE (period, volume-weighted):** {overall:.1%} "
        f"(Availability {avail:.1%}, Performance {perf:.1%}, "
        f"Quality {qual:.1%})"
    )
    lines.append("")
    lines.append("## OEE — latest day, by line and shift")
    lines.append("")
    lines.append("| Line | Shift | Availability | Performance | Quality | OEE |")
    lines.append("|------|-------|-------------:|------------:|--------:|----:|")
    for _, r in latest.iterrows():
        lines.append(
            f"| {r['line']} | {r['shift']} | {r['availability']:.1%} | "
            f"{r['performance']:.1%} | {r['quality']:.1%} | **{r['oee']:.1%}** |"
        )
    lines.append("")
    lines.append("## Top losses (whole period)")
    lines.append("")
    lines.append("| Rank | Downtime reason | Minutes lost | Share | Cumulative |")
    lines.append("|-----:|----------------|-------------:|------:|-----------:|")
    for i, (_, r) in enumerate(pareto.head(5).iterrows(), start=1):
        lines.append(
            f"| {i} | {r['downtime_reason']} | {int(r['downtime_minutes'])} | "
            f"{r['share_pct']:.1f}% | {r['cum_pct']:.1f}% |"
        )
    lines.append("")
    lines.append("## Recommended actions for the incoming shift")
    lines.append("")
    for _, r in latest.iterrows():
        lines.append(f"### {r['line']} — {r['shift']} shift (OEE {r['oee']:.1%})")
        for a in recommended_actions(r, worst_reason):
            lines.append(f"- {a}")
        lines.append("")
    lines.append(
        "_Note: figures are computed from the sample shift logs. "
        "Downtime reasons come from operator-entered shift records; "
        "'No Reason Recorded' rows should be chased down at the line._"
    )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="OEE Production Line Monitor")
    parser.add_argument(
        "--input", required=True, help="Shift-log CSV (see data/shift_logs.csv)"
    )
    parser.add_argument(
        "--out", required=True, help="Output directory for CSV, PNG and report"
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_shift_logs(input_path)
    df, summary = compute_oee(df)
    pareto = downtime_pareto(df)

    summary_path = out_dir / "oee_summary.csv"
    summary.to_csv(summary_path, index=False)
    pareto_path = out_dir / "downtime_pareto.png"
    plot_pareto(pareto, pareto_path)
    report_path = out_dir / "handover_report.md"
    write_handover_report(df, summary, pareto, report_path)

    avail, perf, qual, overall = overall_oee(df)
    print(f"Rows loaded:            {len(df)}")
    print(f"Date range:             {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"Lines:                  {', '.join(sorted(df['line'].unique()))}")
    print(f"Overall OEE:            {overall:.1%} (volume-weighted)")
    print(f"Overall Availability:   {avail:.1%}")
    print(f"Overall Performance:    {perf:.1%}")
    print(f"Overall Quality:        {qual:.1%}")
    print(f"Total downtime:         {int(df['downtime_minutes'].sum())} minutes")
    print("Top downtime reasons:")
    for _, r in pareto.head(3).iterrows():
        print(
            f"  - {r['downtime_reason']}: {int(r['downtime_minutes'])} min "
            f"({r['share_pct']:.1f}%)"
        )
    print(f"Wrote {summary_path}")
    print(f"Wrote {pareto_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
