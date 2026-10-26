"""Core hotel KPI calculations: occupancy, ADR, RevPAR and breakdowns."""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Dict, Iterable, List

REQUIRED_COLUMNS = {
    "booking_id", "room_type", "channel", "check_in", "check_out", "nightly_rate", "status",
}


@dataclass(frozen=True)
class Booking:
    booking_id: str
    room_type: str
    channel: str
    check_in: date
    check_out: date
    nightly_rate: float
    status: str

    @property
    def is_cancelled(self) -> bool:
        return self.status.strip().lower() == "cancelled"

    def nights_between(self, start: date, end: date) -> List[date]:
        """Nights of this stay that fall within [start, end], both inclusive."""
        first = max(self.check_in, start)
        last = min(self.check_out - timedelta(days=1), end)
        return [first + timedelta(days=i) for i in range((last - first).days + 1)]


@dataclass(frozen=True)
class KPIs:
    room_nights_available: int
    room_nights_sold: int
    revenue: float
    occupancy: float
    adr: float
    revpar: float


def load_bookings(path: str) -> List[Booking]:
    """Read bookings from a CSV file, validating columns and dates."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")

        bookings = []
        for line_no, row in enumerate(reader, start=2):
            check_in = date.fromisoformat(row["check_in"])
            check_out = date.fromisoformat(row["check_out"])
            if check_out <= check_in:
                raise ValueError(f"line {line_no}: check_out must be after check_in")
            bookings.append(Booking(
                booking_id=row["booking_id"],
                room_type=row["room_type"],
                channel=row["channel"],
                check_in=check_in,
                check_out=check_out,
                nightly_rate=float(row["nightly_rate"]),
                status=row["status"],
            ))
        return bookings


def _period_nights(start: date, end: date) -> int:
    if end < start:
        raise ValueError("end date must be on or after start date")
    return (end - start).days + 1


def compute_kpis(bookings: Iterable[Booking], total_rooms: int, start: date, end: date) -> KPIs:
    """Headline KPIs for the period. Cancelled bookings are excluded."""
    available = total_rooms * _period_nights(start, end)
    sold = 0
    revenue = 0.0
    for b in bookings:
        if b.is_cancelled:
            continue
        nights = len(b.nights_between(start, end))
        sold += nights
        revenue += nights * b.nightly_rate

    return KPIs(
        room_nights_available=available,
        room_nights_sold=sold,
        revenue=round(revenue, 2),
        occupancy=sold / available if available else 0.0,
        adr=round(revenue / sold, 2) if sold else 0.0,
        revpar=round(revenue / available, 2) if available else 0.0,
    )


def breakdown(
    bookings: Iterable[Booking], start: date, end: date, key: Callable[[Booking], str]
) -> Dict[str, dict]:
    """Room nights, revenue, ADR and revenue share grouped by `key` (e.g. channel)."""
    nights_by: Dict[str, int] = defaultdict(int)
    revenue_by: Dict[str, float] = defaultdict(float)
    for b in bookings:
        if b.is_cancelled:
            continue
        nights = len(b.nights_between(start, end))
        if nights:
            nights_by[key(b)] += nights
            revenue_by[key(b)] += nights * b.nightly_rate

    total_revenue = sum(revenue_by.values())
    result = {}
    for group in sorted(revenue_by, key=revenue_by.get, reverse=True):
        result[group] = {
            "room_nights": nights_by[group],
            "revenue": round(revenue_by[group], 2),
            "adr": round(revenue_by[group] / nights_by[group], 2),
            "revenue_share": revenue_by[group] / total_revenue if total_revenue else 0.0,
        }
    return result


def daily_occupancy(
    bookings: Iterable[Booking], total_rooms: int, start: date, end: date
) -> Dict[date, float]:
    """Occupancy for each night in the period."""
    sold: Dict[date, int] = {start + timedelta(days=i): 0 for i in range(_period_nights(start, end))}
    for b in bookings:
        if not b.is_cancelled:
            for night in b.nights_between(start, end):
                sold[night] += 1
    return {night: count / total_rooms for night, count in sold.items()}


def cancellation_rate(bookings: Iterable[Booking], start: date, end: date) -> float:
    """Share of bookings arriving in the period that were cancelled."""
    arriving = [b for b in bookings if start <= b.check_in <= end]
    if not arriving:
        return 0.0
    return sum(b.is_cancelled for b in arriving) / len(arriving)


def build_report(bookings: List[Booking], total_rooms: int, start: date, end: date) -> dict:
    """Everything the CLI prints, as plain data."""
    kpis = compute_kpis(bookings, total_rooms, start, end)
    daily = daily_occupancy(bookings, total_rooms, start, end)
    busiest = max(daily, key=daily.get)
    quietest = min(daily, key=daily.get)

    weekend_nights = [d for d in daily if d.weekday() in (4, 5)]  # Fri and Sat nights
    weekday_nights = [d for d in daily if d.weekday() not in (4, 5)]

    def avg(nights: List[date]) -> float:
        return sum(daily[d] for d in nights) / len(nights) if nights else 0.0

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat(), "rooms": total_rooms},
        "kpis": {
            "occupancy": kpis.occupancy,
            "adr": kpis.adr,
            "revpar": kpis.revpar,
            "revenue": kpis.revenue,
            "room_nights_sold": kpis.room_nights_sold,
            "room_nights_available": kpis.room_nights_available,
            "cancellation_rate": cancellation_rate(bookings, start, end),
        },
        "occupancy_pattern": {
            "weekday_avg": avg(weekday_nights),
            "weekend_avg": avg(weekend_nights),
            "busiest_night": {"date": busiest.isoformat(), "occupancy": daily[busiest]},
            "quietest_night": {"date": quietest.isoformat(), "occupancy": daily[quietest]},
        },
        "by_channel": breakdown(bookings, start, end, key=lambda b: b.channel),
        "by_room_type": breakdown(bookings, start, end, key=lambda b: b.room_type),
    }
