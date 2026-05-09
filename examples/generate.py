"""Generate the three named input profiles used in the comparison runs.
Usage: python examples/generate.py
Writes morning_rush.csv, midday_random.csv, evening_down.csv into this dir.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

FLOORS = 60
COUNT = 200
HORIZON = 600
SEED = 42

def morning_rush():
    """Most passengers entering from floor 1, going up."""
    rng = random.Random(SEED)
    rows = []
    for i in range(COUNT):
        t = int(rng.expovariate(1 / 30))  # bursty start
        if rng.random() < 0.85:
            src = 1
            dst = rng.randint(2, FLOORS)
        else:
            src, dst = rng.sample(range(1, FLOORS + 1), 2)
        rows.append((t, f"p{i}", src, dst))
    return rows

def midday_random():
    """Uniform random source/dest, uniform request times."""
    rng = random.Random(SEED + 1)
    rows = []
    for i in range(COUNT):
        t = rng.randint(0, HORIZON)
        src, dst = rng.sample(range(1, FLOORS + 1), 2)
        rows.append((t, f"p{i}", src, dst))
    return rows

def evening_down():
    """Most passengers leaving the building, going to floor 1."""
    rng = random.Random(SEED + 2)
    rows = []
    for i in range(COUNT):
        t = rng.randint(0, HORIZON)
        if rng.random() < 0.85:
            src = rng.randint(2, FLOORS)
            dst = 1
        else:
            src, dst = rng.sample(range(1, FLOORS + 1), 2)
        rows.append((t, f"p{i}", src, dst))
    return rows

def write(rows, path: Path):
    rows = sorted(rows, key=lambda r: r[0])
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "id", "source", "dest"])
        w.writerows(rows)


if __name__ == "__main__":
    here = Path(__file__).parent
    write(morning_rush(), here / "morning_rush.csv")
    write(midday_random(), here / "midday_random.csv")
    write(evening_down(), here / "evening_down.csv")
    print(f"Wrote 3 profiles to {here}")
