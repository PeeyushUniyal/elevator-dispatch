"""CSV I/O."""
from __future__ import annotations

import csv
from pathlib import Path

from .models import Passenger, Request

def read_requests(path: str | Path, floors: int | None = None) -> list[Request]:
    requests: list[Request] = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            req = Request(
                time=int(row["time"]),
                id=row["id"],
                source=int(row["source"]),
                dest=int(row["dest"]),
            )
            if floors is not None and not (
                1 <= req.source <= floors and 1 <= req.dest <= floors
            ):
                continue
            requests.append(req)
    return requests

def write_positions(
    path: str | Path, position_log: list[tuple[int, list[int]]]
) -> None:
    if not position_log:
        Path(path).write_text("")
        return
    n_elevators = len(position_log[0][1])
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time"] + [f"e{i}" for i in range(n_elevators)])
        for t, floors in position_log:
            writer.writerow([t] + floors)

def write_passengers(path: str | Path, passengers: list[Passenger]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "source", "dest", "request_time", "board_time",
            "arrival_time", "elevator_id", "wait_time", "travel_time", "total_time",
        ])
        for p in passengers:
            writer.writerow([
                p.id, p.source, p.dest, p.request_time, p.board_time,
                p.arrival_time, p.assigned_elevator_id,
                p.wait_time, p.travel_time, p.total_time,
            ])