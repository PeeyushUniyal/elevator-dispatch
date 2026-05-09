"""Summary statistics and an optional histogram of total_time."""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

from .models import Passenger

@dataclass
class Stats:
    count: int
    min: float
    max: float
    avg: float
    p50: float
    p90: float
    p99: float

def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def compute_stats(values: list[float]) -> Stats:
    if not values:
        return Stats(0, 0, 0, 0, 0, 0, 0)
    return Stats(
        count=len(values),
        min=min(values),
        max=max(values),
        avg=statistics.mean(values),
        p50=_percentile(values, 50),
        p90=_percentile(values, 90),
        p99=_percentile(values, 99),
    )

def write_summary(path: str | Path, passengers: list[Passenger]) -> None:
    waits = [p.wait_time for p in passengers if p.wait_time is not None]
    totals = [p.total_time for p in passengers if p.total_time is not None]
    wait_stats = compute_stats(waits)
    total_stats = compute_stats(totals)

    lines = [f"Passengers served: {wait_stats.count}", "", "Wait time:"]
    for k, v in asdict(wait_stats).items():
        lines.append(f"  {k}: {v}")
    lines += ["", "Total time:"]
    for k, v in asdict(total_stats).items():
        lines.append(f"  {k}: {v}")
    Path(path).write_text("\n".join(lines) + "\n")

def plot_distribution(path: str | Path, passengers: list[Passenger]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    totals = [p.total_time for p in passengers if p.total_time is not None]
    if not totals:
        return
    plt.figure(figsize=(8, 5))
    plt.hist(totals, bins=20)
    plt.xlabel("total_time (ticks)")
    plt.ylabel("passengers")
    plt.title("Distribution of total_time")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
