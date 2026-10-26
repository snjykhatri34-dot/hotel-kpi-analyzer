"""Command-line entry point: python -m hotel_kpi bookings.csv --rooms 40"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from typing import List, Optional

from .metrics import build_report, load_bookings


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _money(x: float) -> str:
    return f"${x:,.2f}"


def render_text(report: dict) -> str:
    p, k, o = report["period"], report["kpis"], report["occupancy_pattern"]
    lines = [
        f"Hotel KPI report: {p['start']} to {p['end']} ({p['rooms']} rooms)",
        "",
        f"  Occupancy          {_pct(k['occupancy'])}",
        f"  ADR                {_money(k['adr'])}",
        f"  RevPAR             {_money(k['revpar'])}",
        f"  Room revenue       {_money(k['revenue'])}",
        f"  Room nights sold   {k['room_nights_sold']:,} of {k['room_nights_available']:,}",
        f"  Cancellation rate  {_pct(k['cancellation_rate'])}",
        "",
        "Occupancy pattern",
        f"  Weekday nights     {_pct(o['weekday_avg'])}",
        f"  Fri/Sat nights     {_pct(o['weekend_avg'])}",
        f"  Busiest night      {o['busiest_night']['date']} ({_pct(o['busiest_night']['occupancy'])})",
        f"  Quietest night     {o['quietest_night']['date']} ({_pct(o['quietest_night']['occupancy'])})",
    ]
    for title, groups in (("By channel", report["by_channel"]), ("By room type", report["by_room_type"])):
        lines += ["", title, f"  {'':<14}{'Nights':>8}{'Revenue':>14}{'ADR':>10}{'Share':>8}"]
        for name, g in groups.items():
            lines.append(
                f"  {name:<14}{g['room_nights']:>8,}{_money(g['revenue']):>14}"
                f"{_money(g['adr']):>10}{_pct(g['revenue_share']):>8}"
            )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hotel_kpi", description="Occupancy, ADR and RevPAR from a bookings CSV."
    )
    parser.add_argument("csv", help="bookings CSV (see README for columns)")
    parser.add_argument("--rooms", type=int, required=True, help="total rooms in the property")
    parser.add_argument("--start", type=date.fromisoformat, help="first night, YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, help="last night, YYYY-MM-DD")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a text report")
    args = parser.parse_args(argv)

    try:
        bookings = load_bookings(args.csv)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if not bookings:
        print("error: no bookings in file", file=sys.stderr)
        return 1

    # Default to the span of the data: first arrival through the last occupied night.
    start = args.start or min(b.check_in for b in bookings)
    end = args.end or max(b.check_out for b in bookings) - timedelta(days=1)
    if end < start:
        print("error: --end must be on or after --start", file=sys.stderr)
        return 1

    report = build_report(bookings, args.rooms, start, end)
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return 0
