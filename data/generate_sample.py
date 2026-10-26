"""Generate a realistic-looking sample bookings file (fictional data).

Usage: python data/generate_sample.py > data/sample_bookings.csv
"""
import csv
import random
import sys
from datetime import date, timedelta

ROOMS = {"Standard": 24, "Deluxe": 12, "Suite": 4}
BASE_RATE = {"Standard": 109, "Deluxe": 159, "Suite": 259}
CHANNELS = [("Direct", 0.35), ("Booking.com", 0.30), ("Expedia", 0.20), ("Walk-in", 0.15)]
START, DAYS = date(2026, 1, 1), 90


def main(seed: int = 7) -> None:
    rng = random.Random(seed)
    occupied = {rt: [0] * (DAYS + 14) for rt in ROOMS}
    writer = csv.writer(sys.stdout)
    writer.writerow(["booking_id", "room_type", "channel", "check_in", "check_out", "nightly_rate", "status"])

    booking_no = 1000
    for day in range(DAYS):
        weekend = (START + timedelta(days=day)).weekday() in (4, 5)
        for _ in range(rng.randint(10, 16) if weekend else rng.randint(5, 11)):
            room_type = rng.choices(list(ROOMS), weights=[60, 30, 10])[0]
            nights = rng.choices([1, 2, 3, 4, 5, 7], weights=[30, 30, 18, 10, 7, 5])[0]
            cancelled = rng.random() < 0.08
            span = range(day, day + nights)
            if not cancelled and any(occupied[room_type][d] >= ROOMS[room_type] for d in span):
                continue  # sold out for this stay
            if not cancelled:
                for d in span:
                    occupied[room_type][d] += 1

            rate = BASE_RATE[room_type] * (1.18 if weekend else 1.0) * rng.uniform(0.9, 1.1)
            check_in = START + timedelta(days=day)
            booking_no += 1
            writer.writerow([
                f"B{booking_no}",
                room_type,
                rng.choices([c for c, _ in CHANNELS], weights=[w for _, w in CHANNELS])[0],
                check_in.isoformat(),
                (check_in + timedelta(days=nights)).isoformat(),
                f"{rate:.2f}",
                "cancelled" if cancelled else "confirmed",
            ])


if __name__ == "__main__":
    main()
