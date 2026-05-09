"""Discrete-time simulation loop.
Each tick: admit due requests, snapshot positions, process the current floor
of every elevator (drop-offs before pickups), then step one floor.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Elevator, Passenger, Request, Stop, StopType
from .scheduler import Scheduler

@dataclass
class Simulation:
    elevators: list[Elevator]
    scheduler: Scheduler
    requests: list[Request]
    clock: int = 0
    active_passengers: dict[str, Passenger] = field(default_factory=dict)
    completed: list[Passenger] = field(default_factory=list)
    position_log: list[tuple[int, list[int]]] = field(default_factory=list)

    def __post_init__(self):
        self.requests = sorted(self.requests, key=lambda r: r.time)

    def is_finished(self) -> bool:
        return (
            not self.requests
            and not self.active_passengers
            and all(not e.plan for e in self.elevators)
        )

    def step(self) -> None:
        while self.requests and self.requests[0].time <= self.clock:
            self._admit(self.requests.pop(0))

        self.position_log.append(
            (self.clock, [e.current_floor for e in self.elevators])
        )

        for elevator in self.elevators:
            self._process_floor(elevator)

        for elevator in self.elevators:
            elevator.advance()

        self.clock += 1

    def run(self, max_ticks: int = 100_000) -> None:
        while not self.is_finished() and self.clock < max_ticks:
            self.step()

    def _admit(self, request: Request) -> None:
        if request.source == request.dest:
            return

        result = self.scheduler.assign(
            request, self.elevators, self.active_passengers, self.clock
        )
        elevator = next(e for e in self.elevators if e.id == result.elevator_id)
        passenger = Passenger(
            id=request.id,
            source=request.source,
            dest=request.dest,
            request_time=request.time,
            assigned_elevator_id=elevator.id,
        )
        self.active_passengers[passenger.id] = passenger
        elevator.plan.insert(
            result.pickup_index, Stop(request.source, StopType.PICKUP, request.id)
        )
        elevator.plan.insert(
            result.dropoff_index, Stop(request.dest, StopType.DROPOFF, request.id)
        )

    def _process_floor(self, elevator: Elevator) -> None:
        # drop off first so capacity is free for new boarders
        stops_here: list[Stop] = []
        while elevator.plan and elevator.plan[0].floor == elevator.current_floor:
            stops_here.append(elevator.plan.pop(0))

        for stop in sorted(stops_here, key=lambda s: 0 if s.type == StopType.DROPOFF else 1):
            if stop.type == StopType.DROPOFF:
                passenger = next(p for p in elevator.onboard if p.id == stop.passenger_id)
                passenger.arrival_time = self.clock
                elevator.onboard.remove(passenger)
                del self.active_passengers[passenger.id]
                self.completed.append(passenger)
            else:  # PICKUP
                passenger = self.active_passengers[stop.passenger_id]
                passenger.board_time = self.clock
                elevator.onboard.append(passenger)
