from elevator.models import Elevator, Passenger, Request, Stop, StopType
from elevator.scheduler import InsertionCostScheduler, NearestCarScheduler

def test_nearest_car_picks_closer_elevator():
    elevators = [
        Elevator(id=0, capacity=4, current_floor=1),
        Elevator(id=1, capacity=4, current_floor=10),
    ]
    request = Request(time=0, id="p", source=8, dest=15)
    result = NearestCarScheduler().assign(request, elevators, {}, now=0)
    assert result.elevator_id == 1

def test_nearest_car_tie_breaks_lowest_id():
    elevators = [
        Elevator(id=0, capacity=4, current_floor=5),
        Elevator(id=1, capacity=4, current_floor=5),
    ]
    request = Request(time=0, id="p", source=5, dest=10)
    result = NearestCarScheduler().assign(request, elevators, {}, now=0)
    assert result.elevator_id == 0

def test_insertion_skips_full_elevator():
    full = Elevator(id=0, capacity=2, current_floor=1)
    full.onboard = [
        Passenger(id="a", source=1, dest=10, request_time=0, assigned_elevator_id=0),
        Passenger(id="b", source=1, dest=10, request_time=0, assigned_elevator_id=0),
    ]
    full.plan = [Stop(10, StopType.DROPOFF, "a"), Stop(10, StopType.DROPOFF, "b")]
    free = Elevator(id=1, capacity=2, current_floor=4)

    request = Request(time=0, id="c", source=3, dest=8)
    in_flight = {p.id: p for p in full.onboard}
    result = InsertionCostScheduler().assign(request, [full, free], in_flight, now=0)

    # Free elevator (closer + empty plan) must be cheaper than detouring
    # the full elevator after its dropoffs.
    assert result.elevator_id == 1

def test_insertion_picks_cheapest_position():
    # Single elevator at floor 1 with an existing trip 1 -> 20.
    # New request 1 -> 5 should be inserted as (pickup at 0, dropoff at 1)
    # so the new passenger is dropped off en route, not after the long trip.
    elevator = Elevator(id=0, capacity=4, current_floor=1)
    existing = Passenger(id="a", source=1, dest=20, request_time=0, assigned_elevator_id=0)
    elevator.onboard = [existing]
    elevator.plan = [Stop(20, StopType.DROPOFF, "a")]

    request = Request(time=0, id="b", source=1, dest=5)
    result = InsertionCostScheduler().assign(
        request, [elevator], {"a": existing}, now=0
    )
    # b's pickup should come before a's dropoff; b's dropoff should come before a's
    # because dropping b at floor 5 is on the way to floor 20.
    assert result.pickup_index == 0
    assert result.dropoff_index == 1
