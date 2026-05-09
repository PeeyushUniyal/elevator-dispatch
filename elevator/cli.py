"""Command-line entry point.
    python -m elevator simulate --input examples/tiny.csv --output runs/tiny
    python -m elevator compare  --input-dir examples --output runs/comparison
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .io import read_requests, write_passengers, write_positions
from .models import Elevator
from .scheduler import SCHEDULERS
from .simulation import Simulation
from .stats import plot_distribution, write_summary

def main() -> None:
    parser = argparse.ArgumentParser(prog="elevator")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    simulate_parser = subparsers.add_parser("simulate", help="Run a single simulation")
    simulate_parser.add_argument("--input", required=True)
    simulate_parser.add_argument("--output", required=True)
    simulate_parser.add_argument("--elevators", type=int, default=4)
    simulate_parser.add_argument("--floors", type=int, default=60)
    simulate_parser.add_argument("--capacity", type=int, default=12)
    simulate_parser.add_argument("--scheduler", choices=SCHEDULERS, default="insertion")

    compare_parser = subparsers.add_parser("compare", help="Run all schedulers on each CSV in a directory")
    compare_parser.add_argument("--input-dir", required=True)
    compare_parser.add_argument("--output", required=True)
    compare_parser.add_argument("--elevators", type=int, default=4)
    compare_parser.add_argument("--floors", type=int, default=60)
    compare_parser.add_argument("--capacity", type=int, default=12)

    args = parser.parse_args()
    if args.cmd == "simulate":
        run_simulation(
            input_path=Path(args.input),
            output_dir=Path(args.output),
            scheduler_name=args.scheduler,
            elevators=args.elevators,
            floors=args.floors,
            capacity=args.capacity,
        )
    elif args.cmd == "compare":
        run_compare(
            input_dir=Path(args.input_dir),
            output_dir=Path(args.output),
            elevators=args.elevators,
            floors=args.floors,
            capacity=args.capacity,
        )

def run_simulation(
    *,
    input_path: Path,
    output_dir: Path,
    scheduler_name: str,
    elevators: int,
    floors: int,
    capacity: int,
) -> None:
    requests = read_requests(input_path, floors=floors)
    fleet = [Elevator(id=i, capacity=capacity) for i in range(elevators)]
    scheduler = SCHEDULERS[scheduler_name]()
    sim = Simulation(elevators=fleet, scheduler=scheduler, requests=requests)
    sim.run()

    output_dir.mkdir(parents=True, exist_ok=True)
    write_positions(output_dir / "positions.csv", sim.position_log)
    write_passengers(output_dir / "passengers.csv", sim.completed)
    write_summary(output_dir / "summary.txt", sim.completed)
    plot_distribution(output_dir / "distribution.png", sim.completed)
    print(f"[{scheduler_name}] {input_path.name}: {len(sim.completed)} served in {sim.clock} ticks -> {output_dir}")

def run_compare(
    *,
    input_dir: Path,
    output_dir: Path,
    elevators: int,
    floors: int,
    capacity: int,
) -> None:
    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        print(f"No CSVs found in {input_dir}")
        return
    for csv_path in csv_files:
        for sched_name in SCHEDULERS:
            run_simulation(
                input_path=csv_path,
                output_dir=output_dir / f"{csv_path.stem}_{sched_name}",
                scheduler_name=sched_name,
                elevators=elevators,
                floors=floors,
                capacity=capacity,
            )