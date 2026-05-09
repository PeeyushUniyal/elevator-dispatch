from elevator.models import Elevator, Request
from elevator.scheduler import InsertionCostScheduler, NearestCarScheduler
from elevator.simulation import Simulation

def make_sim(requests, n_elevators=1, capacity=4, scheduler=None):
    if scheduler is None:
        scheduler = InsertionCostScheduler()
    elevators = [Elevator(id=i, capacity=capacity) for i in range(n_elevators)]
    return Simulation(elevators=elevators, scheduler=scheduler, requests=requests)

def test_single_passenger_end_to_end():
    sim = make_sim([Request(time=0, id="a", source=1, dest=5)])
    sim.run()
    assert len(sim.completed) == 1
    p = sim.completed[0]
    assert p.wait_time == 0
    assert p.travel_time == 4
    assert p.total_time == 4

def test_empty_input_terminates_at_zero():
    sim = make_sim([])
    sim.run()
    assert sim.clock == 0
    assert sim.completed == []

def test_source_equals_dest_is_rejected():
    sim = make_sim([Request(time=0, id="a", source=3, dest=3)])
    sim.run()
    assert sim.completed == []

def test_capacity_respected_three_passengers():
    # three passengers, capacity 2 — the third has to wait for a spot
    requests = [
        Request(time=0, id=f"p{i}", source=1, dest=10) for i in range(3)
    ]
    sim = make_sim(requests, n_elevators=1, capacity=2)
    sim.run()
    assert len(sim.completed) == 3
    assert all(p.wait_time >= 0 and p.travel_time > 0 for p in sim.completed)

def test_two_elevators_share_load():
    # one request near each elevator — load should split
    elevators = [
        Elevator(id=0, capacity=2, current_floor=1),
        Elevator(id=1, capacity=2, current_floor=20),
    ]
    requests = [
        Request(time=0, id="a", source=2, dest=10),
        Request(time=0, id="b", source=19, dest=5),
    ]
    sim = Simulation(
        elevators=elevators, scheduler=NearestCarScheduler(), requests=requests
    )
    sim.run()
    assert len(sim.completed) == 2
    a = next(p for p in sim.completed if p.id == "a")
    b = next(p for p in sim.completed if p.id == "b")
    assert a.assigned_elevator_id == 0
    assert b.assigned_elevator_id == 1

def test_late_request_still_served():
    requests = [
        Request(time=0, id="a", source=1, dest=5),
        Request(time=20, id="b", source=8, dest=2),
    ]
    sim = make_sim(requests, n_elevators=1, capacity=4)
    sim.run()
    assert len(sim.completed) == 2
    b = next(p for p in sim.completed if p.id == "b")
    assert b.request_time == 20
    assert b.board_time >= 20
