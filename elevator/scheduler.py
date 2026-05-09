"""Scheduling strategies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .models import Elevator, Passenger, Request, Stop, StopType

@dataclass
class AssignmentResult:
    elevator_id: int
    pickup_index: int
    dropoff_index: int

@dataclass
class _Insertion:
    pickup_index: int
    dropoff_index: int
    cost: float

WeightFn = Callable[[Passenger], float]

def _predict_arrivals(elevator: Elevator, plan: list[Stop]) -> dict[str, int]:
    """Tick (relative to now) at which each passenger reaches their dropoff."""
    floor = elevator.current_floor
    elapsed = 0
    arrivals: dict[str, int] = {}
    for stop in plan:
        elapsed += abs(stop.floor - floor)
        floor = stop.floor
        if stop.type == StopType.DROPOFF:
            arrivals[stop.passenger_id] = elapsed
    return arrivals

def find_best_insertion(
    elevator: Elevator,
    request: Request,
    active_passengers: dict[str, Passenger],
    weight_fn: WeightFn,
) -> _Insertion | None:
    """Try every (pickup, dropoff) pair in the plan; return the cheapest
    valid one, or None if all of them overflow capacity."""
    best: _Insertion | None = None
    old_arrivals = _predict_arrivals(elevator, elevator.plan)
    n = len(elevator.plan)

    for pickup_idx in range(n + 1):
        for dropoff_idx in range(pickup_idx + 1, n + 2):
            new_plan = list(elevator.plan)
            new_plan.insert(
                pickup_idx, Stop(request.source, StopType.PICKUP, request.id)
            )
            new_plan.insert(
                dropoff_idx, Stop(request.dest, StopType.DROPOFF, request.id)
            )
            if elevator.would_violate_capacity(new_plan):
                continue

            new_arrivals = _predict_arrivals(elevator, new_plan)
            own_total_time = new_arrivals[request.id]

            others_cost = 0.0
            for pid, old_arrival in old_arrivals.items():
                delta = new_arrivals[pid] - old_arrival
                if delta <= 0:
                    continue
                others_cost += weight_fn(active_passengers[pid]) * delta

            cost = own_total_time + others_cost
            if best is None or cost < best.cost:
                best = _Insertion(pickup_idx, dropoff_idx, cost)
    return best

def _append_fallback(elevators: list[Elevator]) -> AssignmentResult:
    """Capacity blocks every insertion. Append to the shortest plan."""
    # TODO: log when this fires — repeated hits mean the building is over-capacity
    target = min(elevators, key=lambda e: (len(e.plan), e.id))
    return AssignmentResult(
        elevator_id=target.id,
        pickup_index=len(target.plan),
        dropoff_index=len(target.plan) + 1,
    )

class Scheduler(Protocol):
    def assign(
        self,
        request: Request,
        elevators: list[Elevator],
        active_passengers: dict[str, Passenger],
        now: int,
    ) -> AssignmentResult: ...

class NearestCarScheduler:
    """Pick the closest elevator. If it can't fit the request, try the next."""

    def assign(self, request, elevators, active_passengers, now):
        by_distance = sorted(
            elevators,
            key=lambda e: (abs(e.current_floor - request.source), e.id),
        )
        for elevator in by_distance:
            ins = find_best_insertion(elevator, request, active_passengers, lambda _p: 1.0)
            if ins is not None:
                return AssignmentResult(elevator.id, ins.pickup_index, ins.dropoff_index)
        return _append_fallback(elevators)

class InsertionCostScheduler:
    """Pick the cheapest insertion across all elevators. Passengers waiting
    longer than aging_threshold get extra weight in the cost — keeps the tail bounded.
    """

    def __init__(self, aging_threshold: int = 30):
        self.aging_threshold = aging_threshold

    def assign(self, request, elevators, active_passengers, now):
        def weight(p: Passenger) -> float:
            return self._aging_weight(p, now)

        best_id: int | None = None
        best_ins: _Insertion | None = None
        for elevator in elevators:
            ins = find_best_insertion(elevator, request, active_passengers, weight)
            if ins is None:
                continue
            if best_ins is None or ins.cost < best_ins.cost:
                best_id = elevator.id
                best_ins = ins

        if best_ins is None:
            return _append_fallback(elevators)
        return AssignmentResult(best_id, best_ins.pickup_index, best_ins.dropoff_index)

    def _aging_weight(self, passenger: Passenger, now: int) -> float:
        wait = now - passenger.request_time
        if wait < self.aging_threshold:
            return 1.0
        return wait / self.aging_threshold

SCHEDULERS: dict[str, type[Scheduler]] = {
    "insertion": InsertionCostScheduler,
    "nearest": NearestCarScheduler,
}
