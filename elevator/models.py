"""Models for the elevator simulation."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

class StopType(Enum):
    PICKUP = "pickup"
    DROPOFF = "dropoff"

@dataclass(frozen=True)
class Request:
    time: int
    id: str
    source: int
    dest: int

@dataclass
class Passenger:
    id: str
    source: int
    dest: int
    request_time: int
    assigned_elevator_id: int
    board_time: int | None = None
    arrival_time: int | None = None

    @property
    def wait_time(self) -> int | None:
        if self.board_time is None:
            return None
        return self.board_time - self.request_time

    @property
    def travel_time(self) -> int | None:
        if self.board_time is None or self.arrival_time is None:
            return None
        return self.arrival_time - self.board_time

    @property
    def total_time(self) -> int | None:
        if self.arrival_time is None:
            return None
        return self.arrival_time - self.request_time

@dataclass
class Stop:
    floor: int
    type: StopType
    passenger_id: str

@dataclass
class Elevator:
    id: int
    capacity: int
    current_floor: int = 1
    onboard: list[Passenger] = field(default_factory=list)
    plan: list[Stop] = field(default_factory=list)

    def advance(self) -> None:
        """Step one floor toward the next stop."""
        if not self.plan:
            return
        target = self.plan[0].floor
        if target > self.current_floor:
            self.current_floor += 1
        elif target < self.current_floor:
            self.current_floor -= 1

    def would_violate_capacity(self, plan: list[Stop]) -> bool:
        load = len(self.onboard)
        for stop in plan:
            load += 1 if stop.type == StopType.PICKUP else -1
            if load > self.capacity:
                return True
        return False
