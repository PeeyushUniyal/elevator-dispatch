# Elevator System Simulation

Python simulator for a destination-dispatch elevator system. Discrete time, configurable fleet, two pluggable schedulers run side by side.

## Quick start

```bash
git clone <repo-url>
cd elevator-dispatch
python -m pip install -r requirements.txt

# generate the three named input profiles
python examples/generate.py

# run a single simulation
python -m elevator simulate --input examples/morning_rush.csv --elevators 4 --floors 60 --capacity 12 --scheduler insertion --output runs/morning_rush

# run all schedulers on every CSV in a directory
python -m elevator compare --input-dir examples --output runs/comparison

# tests
pytest
```

Each run writes four files:

- `positions.csv` — elevator positions per tick
- `passengers.csv` — wait, travel, and total time per passenger
- `summary.txt` — aggregate stats
- `distribution.png` — total-time histogram (if matplotlib's installed)

## Problem

It's a destination-dispatch system. Passengers say where they're going at request time, and the controller picks one elevator and commits to it — no swapping later. The elevator's plan respects capacity and tries to minimize `total_time = wait_time + travel_time` per passenger.

Time moves in integer ticks, where one tick is one floor of vertical travel. The scheduler can't peek into the future request stream, and the simulation ticks forward even across long idle stretches.

Worth saying what this *isn't*: it's not a SCAN/LOOK problem. The whole point of destination dispatch is that the scheduler knows where everyone's going at the moment of request — and the algorithm needs to actually use that.

## Solution

- **Primary scheduler — insertion-cost.** For every new request, score every valid (pickup, dropoff) position in every elevator's plan, take the cheapest. Capacity gets enforced at insertion time by walking the resulting plan and checking nothing overflows.
- **Fairness floor — aging.** The longer a passenger has been waiting, the more it costs to delay them further. Stops the scheduler from indefinitely deferring the same person under sustained load.
- **Baseline — nearest-car.** Picks the closest elevator by current floor, then runs the same insertion logic with no aging weight. Both schedulers share `find_best_insertion`, so the comparison runs isolate exactly two things: how the elevator gets chosen, and whether long-waiting passengers get any extra weight in the cost.

## Architecture

```
elevator-dispatch/
├── elevator/
│   ├── __init__.py
│   ├── __main__.py        # python -m elevator entry
│   ├── models.py          # Request, Passenger, Stop, Elevator, StopType
│   ├── scheduler.py       # Scheduler protocol + InsertionCost + NearestCar + SCHEDULERS
│   ├── simulation.py      # Tick loop
│   ├── io.py              # CSV read/write
│   ├── stats.py           # Summary + histogram
│   └── cli.py             # argparse for simulate / compare
├── tests/
│   ├── test_scheduler.py
│   └── test_simulation.py
└── examples/
    ├── tiny.csv           # 5 hand-checked passengers
    └── generate.py        # writes morning_rush.csv, midday_random.csv, evening_down.csv
```

The `Scheduler` protocol is just `assign(request, elevators, active_passengers, now) -> AssignmentResult`. For a new strategy, we just need to add a new class, one line in `SCHEDULERS`. Nothing else changes.

## Assumptions

| # | Assumption | Alternative | Why |
|---|------------|-------------|-----|
| 1 | Boarding and dropoff happen instantly. | Each one costs 1 tick. | Spec only defines travel cost. A constant board time wouldn't change the algorithm's relative behavior — easy to flip later if it matters. |
| 2 | Direction is whatever the plan says, not a hard physical lock. | SCAN-style direction commitment. | Locking direction throws away the foresight destination dispatch gives you. |
| 3 | Capacity gets checked at insertion time by simulating the resulting plan. | Check at boarding time (assign freely, deny when full). | Boarding-time checks break the "assigned and committed" rule — you'd have to bump someone. |
| 4 | All elevators start at floor 1, idle, empty. | Configurable, or staggered. | Realistic default; spec is silent. |
| 5 | `source == dest` requests get dropped at admission. | Treat as zero-time success. | Either works. Dropping is more honest about probably-bad input. |
| 6 | Floors outside `[1, F]` get dropped at parse time. | Clamp into range. | Silent clamping hides bugs. |
| 7 | Tie on equal cost goes to the lowest elevator id. | Random. | Deterministic runs are easier to debug. Production version would use least-recently-assigned — same determinism, better balance. |
| 8 | Simulation ends when both the request queue and the active-passenger set are empty. | Fixed horizon. | Spec says every passenger has to be served. |
| 9 | Floors are 1-indexed (matches the spec example `source=1`). | 0-indexed. | Match spec. |

## Algorithm: insertion-cost

For each new request `r` at time `now`:

1. For every elevator `e`, try every `(pickup_idx, dropoff_idx)` pair where `pickup_idx < dropoff_idx`:
   - Build the candidate plan with the new pickup and dropoff spliced in.
   - If it overflows capacity at any point, skip.
   - Otherwise score it with the cost function below.
2. Assign to whichever elevator has the cheapest valid insertion.
3. **Fallback:** if nothing's valid anywhere (rare — basically means the building's over capacity), append to the elevator with the shortest plan. Spec requires every request gets served, so this is a deliberate fallback rather than an error.

### Cost function

```
cost(r, e, p_pickup, p_dropoff) =
        delta_total_time(r)
    +   sum over already-assigned q in e:
            aging_weight(q, now) * delta_total_time(q)

aging_weight(q, now) =
        1.0                                       if (now - q.request_time) < aging_threshold
        (now - q.request_time) / aging_threshold  otherwise
```

`aging_threshold` defaults to 30 ticks — about 2× the average wait you'd expect with 4 elevators and 60 floors. Below the threshold the weight is 1.0; above it, the weight grows linearly. So delaying someone who's already waited 90 ticks costs 3× as much as delaying someone who's waited 30.

### Why this scheduler

| Option | Why not |
|--------|---------|
| Round-robin | Ignores geometry. Fair but slow. |
| Zone-based | Needs prior knowledge of traffic patterns. With uniform input it's basically round-robin. |
| Nearest-car (kept as the baseline) | Greedy on geometry. Useful as a control — same insertion logic, but no aging and only looks at the closest elevator. |
| Insertion-cost (chosen) | Considers all elevators. Aging keeps the tail bounded. |

### What it doesn't do

- **No re-optimization.** Spec says assignments are irrevocable. This would need to be changed in production — see Limitations.
- **No future prediction.** Spec forbids look-ahead.

## Complexity

Let `E` = elevators, `P` = pending stops per elevator.

| Operation | Cost |
|-----------|------|
| Per-tick advancement | O(E) |
| Boarding/dropoff at current floor | O(P) per elevator |
| Scheduling a new request | O(E · P²) — every elevator has O(P²) pickup/dropoff position pairs, each one evaluated in O(P) |


At extreme scale (E=50, P=1000+) insertion-cost would slow down. Production fixes: maintain incremental cost tables instead of recomputing each time, or fall back to nearest-car under load. Neither's needed for the input scales here.

## Tests

Ten tests across two layers.

**Scheduler unit tests** (`tests/test_scheduler.py`)
- nearest-car picks the closer elevator
- nearest-car ties go to the lowest id
- insertion-cost skips an elevator that would overflow capacity
- insertion-cost picks the position that drops the new passenger en route, not after a long detour

**Simulation integration tests** (`tests/test_simulation.py`)
- single passenger end-to-end — wait, travel, and total times all check out
- empty input terminates at clock 0
- `source == dest` requests get rejected
- three passengers + capacity 2: all served, no negative timings
- two requests from opposite ends → load splits across two elevators
- a request that arrives late in the run still gets served

Each integration test uses small enough inputs that I traced them by hand against the tick log.

## Comparison: insertion-cost vs nearest-car

200 requests over a 600-tick horizon, 4 elevators / 60 floors / capacity 12.

Quick percentile reminder: **p50** is the median (half the riders wait less, half more), **p90** is the 90th percentile (the worst 10% wait longer than this), **p99** is the 99th percentile — basically the experience of the unluckiest 1% of riders.

| Profile | Scheduler | avg wait | p50 wait | p90 wait | p99 wait | max wait | avg total | p99 total | sim ticks |
|---------|-----------|---------:|---------:|---------:|---------:|---------:|----------:|----------:|----------:|
| Morning rush  | insertion-cost | 108 | 105 | 213 | 261 | 267  | 139 | 300  | 395 |
| Morning rush  | nearest-car    | 320 | 215 | 818 | 958 | 1012 | 352 | 1015 | 1140 |
| Midday random | insertion-cost | 12  | 8   | 30  | 51  | 54   | 34  | 93   | 655 |
| Midday random | nearest-car    | 15  | 7   | 44  | 114 | 148  | 44  | 137  | 689 |
| Evening down  | insertion-cost | 17  | 12  | 44  | 59  | 75   | 46  | 118  | 662 |
| Evening down  | nearest-car    | 43  | 25  | 114 | 172 | 204  | 89  | 220  | 745 |

Reproduce:

```bash
python examples/generate.py
python -m elevator compare --input-dir examples --output runs/comparison
```

### What the numbers say

- **Morning rush** is where insertion-cost wins biggest — about 3× on average wait, 3.7× on p99. Nearest-car keeps piling onto whichever elevator's at the lobby; the others just sit. Insertion-cost spreads the load by looking at global cost.
- **Midday random** narrows the gap on the average (12 vs 15) but holds at p99 (51 vs 114). When requests are uncorrelated, geometry already does most of the work — the remaining win comes almost entirely from aging trimming the tail outliers.
- **Evening down** sits in between: ~2.5× on average, ~3× on p99.

Across all three profiles the **p99 multiplier is bigger than the average multiplier**. That's aging doing what it's supposed to: most of the value of cost-aware scheduling shows up at the tail, not the mean. A scheduler that improves the average while making the tail worse just makes the worst-served rider's day worse — which is the wrong trade.

See `runs/comparison/*/distribution.png` for the total-time histograms.

## Trade-offs

**Fairness vs efficiency.** Aging trades a tiny bit of average-case efficiency for a meaningful drop in tail latency. The comparison runs are basically an A/B test of this — nearest-car uses the same insertion logic but no aging, so the gap on each profile is cost-aware selection plus aging combined. Across all three profiles, p99 improves more than the average. For an office or residential building, the unluckiest riders are the ones most likely to complain, so tail latency sounds the right thing to optimize.

**Determinism vs load symmetry.** Lowest-id tie-breaking means elevator 0 sees a bit more load over time. Random tie-breaking would balance better but kills reproducibility. I went with determinism. A production version would use least-recently-assigned — deterministic *and* balanced.

**Insertion-cost vs precomputed plans.** The insertion approach evaluates O(P²) positions per elevator per request. Fine for any reasonable building. Wouldn't work for a system processing thousands of pending requests per second — for that you'd switch to incremental cost-table maintenance.

## Limitations and what would change in production

- **Irrevocable assignment** is the biggest constraint, and the one I'd most want to argue about. In production I'd push for **Pareto-improving re-assignment** — only swap an assignment if no one ends up worse off (every affected passenger's projected total time is unchanged or better). Recovers most of the foresight loss without breaking the rider's expectation that "the elevator displayed at request time is the one that picks me up."
- **No mechanical model.** Real elevators have door-open time, acceleration, per-floor stop overhead. Adding them is just constants in the cost function — algorithm doesn't change.
- **Single-bank assumption.** Real high-rises split elevators into low/mid/high banks, sometimes with sky lobbies. Multi-bank routing happens *above* the scheduler — request routing picks a bank, then the bank-local scheduler is exactly this one.
- **No predictive pre-positioning.** Real buildings have known traffic patterns by hour of day. Pre-positioning idle elevators (lobby in the morning, top floors at end of day) is high-value and out of scope here.
- **Single-process.** Fine for one building. A campus deployment under one controller would need an actor-per-elevator concurrency model.
- **Observability is local.** Just CSVs and a histogram. Production needs streaming metrics: per-elevator utilization, wait-time percentiles by floor and time-of-day, capacity-pressure events, scheduler-decision latency. I'd alert on p99 wait crossing a threshold, and on the fallback path firing at all.

## Future work, ranked

1. **Pareto-improving re-optimization.** Biggest remaining win.
2. **Express elevators** — skip-floor capability. Drops in at the scheduler interface as a constraint check on candidate insertions.
3. **Accessibility-aware scheduling.** Wheelchair and mobility-aid riders, visually-impaired riders with service animals, etc. need different handling — priority weight in the cost function, larger effective capacity footprint (a wheelchair takes the room of ~2 standard riders), longer dwell time at pickup and dropoff. Plugs in as a `profile` field on `Passenger` and a few extra terms in the cost function. Algorithm shape doesn't change.
4. **Predictive pre-positioning** by hour of day.
5. **Multi-bank coordination** for high-rise / sky-lobby buildings.
6. **Property-based tests** with Hypothesis for invariants like no-starvation under arbitrary input.
7. **Animated visualization** for presentation and debugging.
8. **Long-window load-balancing tie-breaker** (least-recently-assigned) replacing lowest-id.
9. **Incremental cost-table maintenance** for very-large-scale deployments.

## Time spent

Around 5 hours, roughly:

- 30 min — framing, assumptions, README skeleton
- 2 hr — core simulation + insertion-cost scheduler + tests
- 2 hr — nearest-car baseline, comparison runs, statistics, plots
- 30 min — README polish, code review, dry-run

## What I'd improve with more time

1. **Pareto-improving re-optimization** — implement it and benchmark against the current scheduler on the same three profiles.
2. **Tune `aging_threshold` empirically** with a sensitivity sweep. The analytic default's defensible but the optimum is profile-dependent.
3. **Event-driven simulation mode** that skips idle ticks, while keeping the tick-based mode for parity with the spec.
4. **Property-based tests** for no-starvation under arbitrary input.
5. **Animated visualization** of elevator movement against the per-tick log.
