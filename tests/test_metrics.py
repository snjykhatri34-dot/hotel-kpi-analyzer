import os
import tempfile
import unittest
from datetime import date

from hotel_kpi.metrics import (
    Booking, breakdown, build_report, cancellation_rate, compute_kpis, daily_occupancy, load_bookings,
)


def booking(bid, check_in, check_out, rate, status="confirmed", room_type="Standard", channel="Direct"):
    return Booking(bid, room_type, channel, date.fromisoformat(check_in), date.fromisoformat(check_out), rate, status)


JAN_1, JAN_3 = date(2026, 1, 1), date(2026, 1, 3)


class NightsBetweenTest(unittest.TestCase):
    def test_stay_fully_inside_period(self):
        b = booking("1", "2026-01-01", "2026-01-03", 100)
        self.assertEqual(b.nights_between(JAN_1, JAN_3), [date(2026, 1, 1), date(2026, 1, 2)])

    def test_stay_clipped_to_period(self):
        b = booking("1", "2025-12-30", "2026-01-05", 100)
        self.assertEqual(len(b.nights_between(JAN_1, JAN_3)), 3)

    def test_stay_outside_period(self):
        b = booking("1", "2026-02-01", "2026-02-02", 100)
        self.assertEqual(b.nights_between(JAN_1, JAN_3), [])


class ComputeKpisTest(unittest.TestCase):
    def test_headline_numbers(self):
        bookings = [
            booking("1", "2026-01-01", "2026-01-03", 100),  # 2 nights, $200
            booking("2", "2026-01-02", "2026-01-04", 150),  # 2 nights, $300
            booking("3", "2026-01-01", "2026-01-02", 999, status="cancelled"),
        ]
        k = compute_kpis(bookings, total_rooms=2, start=JAN_1, end=JAN_3)
        self.assertEqual(k.room_nights_available, 6)
        self.assertEqual(k.room_nights_sold, 4)
        self.assertEqual(k.revenue, 500)
        self.assertAlmostEqual(k.occupancy, 4 / 6)
        self.assertEqual(k.adr, 125)
        self.assertAlmostEqual(k.revpar, round(500 / 6, 2))

    def test_no_sales(self):
        k = compute_kpis([], total_rooms=10, start=JAN_1, end=JAN_3)
        self.assertEqual((k.occupancy, k.adr, k.revpar), (0.0, 0.0, 0.0))

    def test_rejects_reversed_period(self):
        with self.assertRaises(ValueError):
            compute_kpis([], total_rooms=10, start=JAN_3, end=JAN_1)


class BreakdownTest(unittest.TestCase):
    def test_groups_sorted_by_revenue(self):
        bookings = [
            booking("1", "2026-01-01", "2026-01-02", 100, channel="Direct"),
            booking("2", "2026-01-01", "2026-01-03", 120, channel="Expedia"),
        ]
        result = breakdown(bookings, JAN_1, JAN_3, key=lambda b: b.channel)
        self.assertEqual(list(result), ["Expedia", "Direct"])
        self.assertEqual(result["Expedia"]["room_nights"], 2)
        self.assertAlmostEqual(result["Direct"]["revenue_share"], 100 / 340)


class DailyAndCancellationTest(unittest.TestCase):
    def test_daily_occupancy(self):
        bookings = [booking("1", "2026-01-02", "2026-01-03", 100)]
        daily = daily_occupancy(bookings, total_rooms=4, start=JAN_1, end=JAN_3)
        self.assertEqual(daily, {date(2026, 1, 1): 0.0, date(2026, 1, 2): 0.25, date(2026, 1, 3): 0.0})

    def test_cancellation_rate_counts_arrivals_only(self):
        bookings = [
            booking("1", "2026-01-01", "2026-01-02", 100, status="cancelled"),
            booking("2", "2026-01-02", "2026-01-03", 100),
            booking("3", "2026-02-01", "2026-02-02", 100, status="cancelled"),  # outside period
        ]
        self.assertEqual(cancellation_rate(bookings, JAN_1, JAN_3), 0.5)


class LoadBookingsTest(unittest.TestCase):
    def _write(self, text):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_loads_valid_file(self):
        path = self._write(
            "booking_id,room_type,channel,check_in,check_out,nightly_rate,status\n"
            "B1,Suite,Direct,2026-01-01,2026-01-03,250.50,confirmed\n"
        )
        [b] = load_bookings(path)
        self.assertEqual(b.nightly_rate, 250.5)
        self.assertEqual(b.check_out, date(2026, 1, 3))

    def test_missing_column(self):
        path = self._write("booking_id,room_type\nB1,Suite\n")
        with self.assertRaisesRegex(ValueError, "missing columns"):
            load_bookings(path)

    def test_bad_dates(self):
        path = self._write(
            "booking_id,room_type,channel,check_in,check_out,nightly_rate,status\n"
            "B1,Suite,Direct,2026-01-03,2026-01-01,250,confirmed\n"
        )
        with self.assertRaisesRegex(ValueError, "line 2"):
            load_bookings(path)


class SampleDataTest(unittest.TestCase):
    def test_report_on_sample_file(self):
        here = os.path.dirname(__file__)
        bookings = load_bookings(os.path.join(here, "..", "data", "sample_bookings.csv"))
        report = build_report(bookings, 40, date(2026, 1, 1), date(2026, 3, 31))
        self.assertTrue(0 < report["kpis"]["occupancy"] <= 1)
        self.assertAlmostEqual(sum(g["revenue_share"] for g in report["by_channel"].values()), 1.0)


if __name__ == "__main__":
    unittest.main()
