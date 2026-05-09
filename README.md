# Elevator System Simulation

A discrete-time simulation of a Destination Dispatch elevator system, in Python.

## Quick start

```bash
git clone <repo-url>
cd elevator-takehome
python -m pip install -r requirements.txt

# generate the three named input profiles
python examples/generate.py

# run a single simulation
python -m elevator simulate \
    --input examples/morning_rush.csv \
    --elevators 4 --floors 60 --capacity 12 \
    --scheduler insertion \
    --output runs/morning_rush

# run all schedulers on every CSV in a directory
python -m elevator compare --input-dir examples --output runs/comparison

# tests
pytest
```

Each run writes:

- `positions.csv` — per-tick elevator positions
- `passengers.csv` — per-passenger wait, travel, total times
- `summary.txt` — aggregate stats
- `distribution.png` — total-time histogram (if matplotlib is installed)

## Problem framing

The system models **Destination Dispatch**: each passenger declares both source and destination at request time, the controller immediately and irrevocably assigns them to a specific elevator, and the elevator's plan is built to honor capacity and minimize per-passenger `total_time = wait_time + travel_time`. Time advances in integer ticks; one tick is one floor of vertical travel. The controller cannot peek past `now` in the request stream, and the simulation ticks forward continuously even across long idle stretches.

This is not a SCAN/LOOK problem. The controller has full trip information at the moment of assignment, and the algorithm needs to use it.

## Design summary

- **Primary scheduler — insertion-cost.** For each new request, evaluate the marginal cost of every valid insertion position in every elevator's plan; assign to the cheapest valid one. Capacity is enforced at insertion time by simulating projected occupancy along the plan.
- **Fairness floor — aging.** The cost of delaying an already-waiting passenger grows past a threshold, so a sustained burst of new requests can't keep starving someone in the queue.
- **Baseline — nearest-car.** Picks the closest elevator by current floor, then uses the same insertion machinery with uniform-weight cost (no aging). Both schedulers share `find_best_insertion`, so the comparison runs isolate exactly two differences: how the elevator is selected, and whether long-waiting passengers get extra weight.

## Architecture

```
elevator-takehome/
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

The `Scheduler` protocol is `assign(request, elevators, active_passengers, now) -> AssignmentResult`. Adding a new strategy is one new class plus one line in the `SCHEDULERS` dict — no changes to `Simulation` or `Elevator`.

## Assumptions and design decisions

The spec leaves several things unspecified. Each choice below is paired with the alternative I considered.

| # | Assumption | Alternative | Why this choice |
|---|------------|-------------|-----------------|
| 1 | Boarding and dropoff cost 0 ticks. | Each board/drop costs 1 tick. | Spec defines travel cost only. Non-zero board cost is a constant factor; it would not change the algorithm's relative behavior. |
| 2 | Direction is plan-driven, not a hard physical lock. The next stop in the plan dictates which way the elevator moves. | A SCAN-style direction commitment. | The whole point of destination dispatch is that the controller plans the trip; a hard direction commitment discards that information. |
| 3 | Capacity is enforced at insertion time by simulating projected occupancy at every floor along the resulting plan. | Boarding-time enforcement (assign freely, deny boarding when full). | Boarding-time enforcement breaks the "immediately assigned, can't change" rule when an elevator becomes full mid-trip. |
| 4 | All elevators start at floor 1, idle, empty. | Configurable, or staggered. | Realistic default; the spec is silent. |
| 5 | `source == dest`: rejected at admission, not assigned. | Treat as zero-time. | Either is defensible. Rejection is more honest about probable malformed input. |
| 6 | Out-of-range floors are dropped at input parsing. | Clamp into range. | Silent clamping hides bugs. |
| 7 | Tie-break on equal cost: lowest elevator id wins. | Random. | Deterministic runs are easier to debug. A production version would use least-recently-assigned for the same determinism with better balance. |
| 8 | Termination: clock advances until both the future-request queue and the active-passenger set are empty. | Fixed horizon. | The spec requires every passenger be served. |
| 9 | Floors are 1-indexed (matches the spec's `source=1` example). | 0-indexed. | Match spec. |

## Algorithm: insertion-cost

For each new request `r` arriving at time `now`:

1. For each elevator `e`:
   - For each `(pickup_idx, dropoff_idx)` pair with `pickup_idx < dropoff_idx`:
     - Build the candidate plan and reject if it overflows capacity.
     - Compute incremental cost (formula below).
   - Track the cheapest valid insertion for `e`.
2. Assign `r` to the elevator with the global minimum cost.
3. **Fallback:** if no valid insertion exists in any elevator (rare; implies sustained over-capacity), append to the elevator with the shortest plan. The problem requires that every request eventually be served, so this is an explicit fallback rather than an error.

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

`aging_threshold` defaults to 30 ticks (roughly 2× the expected wait for the default 4-elevator / 60-floor configuration). Aging weight is 1.0 below the threshold and grows linearly above it, so deferring a passenger who has waited 90 ticks costs 3× as much as deferring one who has waited 30.

### Why this scheduler

| Option | Rejected because |
|--------|------------------|
| Round-robin | Ignores geometry. Fair but slow. |
| Zone-based | Requires prior knowledge of traffic patterns. With uniform input, degrades to round-robin. |
| Nearest-car (used as baseline) | Greedy on geometry. Useful as a control: it shares plan-insertion logic with insertion-cost but has no aging and only considers the nearest elevator. |
| Insertion-cost (chosen) | Considers all elevators; uses aging weights to bound the tail. |

### What insertion-cost does not do

- It does not re-optimize. The spec says assignments are irrevocable. In production I would push back on this — see Limitations.
- It does not predict future requests. The spec forbids look-ahead.
- It does not coordinate elevators across multiple banks. Out of scope.

## Complexity

Let `E` = elevators, `P` = pending stops per elevator.

| Operation | Cost |
|-----------|------|
| Per-tick advancement | O(E) |
| Boarding / dropoff at current floor | O(P) per elevator |
| Scheduling a new request | O(E · P²) — each elevator has O(P²) insertion-position pairs, each evaluated in O(P) |

For realistic configurations (E=8, P~20) the scheduler is well under 100k ops per request. Not bottlenecked at any reasonable scale.

At extreme scale (E=50, P=1000+) insertion-cost would degrade. Production mitigations: maintain incremental cost tables instead of recomputing, or fall back to nearest-car under load. Neither is needed for the input scales in this submission.

## Tests

Ten tests, two layers:

**Scheduler unit tests** (`tests/test_scheduler.py`)
- nearest-car picks the closer elevator
- nearest-car ties go to the lowest id
- insertion-cost skips an elevator that would overflow capacity
- insertion-cost picks the position that drops the new passenger en route, not after a long detour

**Simulation integration tests** (`tests/test_simulation.py`)
- single passenger end-to-end: wait_time, travel_time, total_time all correct
- empty input terminates at clock 0
- `source == dest` requests are rejected
- three passengers + capacity 2: all served, no negative timings
- two requests from opposite ends → load splits across two elevators
- a request submitted late in the run is still served

Each integration test is small enough to verify by hand on the corresponding tick log.

## Comparison: insertion-cost vs nearest-car

200 requests over a 600-tick horizon, 4 elevators / 60 floors / capacity 12.

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

- **Morning rush** is where insertion-cost wins biggest (~3× on average wait, ~3.7× on p99). Nearest-car serialises onto whichever elevator is at the lobby; the others under-utilise. Insertion-cost spreads the load by considering global cost.
- **Midday random** narrows the gap on the average (12 vs 15) but holds at p99 (51 vs 114). With low-correlation requests, geometry already does most of the work; the remaining win is almost entirely the aging mechanism trimming tail outliers.
- **Evening down** sits between the two: ~2.5× on average, ~3× on p99.

Across all three profiles the **p99 multiplier is larger than the average multiplier**. That is the aging mechanism doing its job: most of the value of cost-aware scheduling shows up in the tail, not the mean. A scheduler that improves the average while inflating the tail is shipping a worse experience to the people least able to afford it.

See `runs/comparison/*/distribution.png` for the total-time histograms.

## Trade-offs

**Fairness vs efficiency.** The aging mechanism trades a small amount of average-case efficiency for a meaningful reduction in tail latency. The comparison runs are effectively this trade-off A/B tested: nearest-car uses the same insertion logic with no aging, so the gap on each profile is the combined effect of cost-aware elevator selection plus aging. The pattern across all three profiles is that p99 improves more than average — that is aging doing what it should. For a residential or office building, where the worst-served users are the ones who churn, tail latency is the right objective.

**Determinism vs load symmetry.** Lowest-id tie-breaking means elevator 0 sees marginally more load over long runs. A random tie-breaker balances better but breaks reproducibility. I chose determinism. A production version would use least-recently-assigned, which is deterministic *and* balanced.

**Insertion-cost vs precomputed plans.** The insertion approach evaluates O(P²) positions per elevator per request. Fine for any building scale. It would be wrong for a system serving thousands of pending requests per second; for that, switch to incremental cost-table maintenance.

## Limitations and what would change in production

- **Irrevocable assignment.** The single biggest design constraint, and the one I would most want to push back on. In production I would advocate for **Pareto-improving re-assignment**: a passenger may be reassigned only if every affected passenger's projected total_time is unchanged or better. This recovers most of the foresight loss without breaking the user contract that *the elevator displayed at request time is the one that picks them up*.
- **No mechanical model.** Real elevators have door-open time, acceleration profiles, per-floor stop overhead. Adding them is mechanical (constants in the cost function); doesn't change the algorithm.
- **Single-bank assumption.** Real high-rises split elevators into low/mid/high banks, often with sky lobbies. Multi-bank routing happens above the scheduler — request routing decides which bank, then the bank-local scheduler is exactly this one.
- **No predictive pre-positioning.** Real buildings have known traffic patterns by hour. Pre-positioning idle elevators (lobby in the morning, top floors at end of day) is high-value and out of scope.
- **Single-process.** Correct at one building's scale. A campus deployment under one controller would need an actor-per-elevator concurrency story.
- **Observability is local.** Currently emits CSVs and a histogram. A production deployment needs streaming metrics: per-elevator utilisation, wait-time percentiles by floor and time-of-day, capacity-pressure events, scheduler-decision latency. I would alert on p99 wait crossing a threshold and on the fallback path firing at all.

## Future work, ranked

1. **Pareto-improving re-optimisation.** Biggest remaining gain.
2. **Express elevators** — skip-floor capability. Drops in at the scheduler interface as a constraint check.
3. **Predictive pre-positioning** by hour-of-day.
4. **Multi-bank coordination** for high-rise / sky-lobby buildings.
5. **Property-based tests** with Hypothesis for invariants like no-starvation under arbitrary input.
6. **Animated visualization** for presentation and debugging.
7. **Long-window load-balancing tie-breaker** (least-recently-assigned) replacing lowest-id.
8. **Incremental cost-table maintenance** for very-large-scale deployments.

## Time spent

Around 5 focused hours, roughly:

- .5hr — framing, assumptions, README skeleton
- 2hr — core simulation + insertion-cost scheduler + tests
- 2hr — nearest-car baseline, comparison runs, statistics, plots
- .5hr — README polish, code review, dry-run

## What I would improve with more time

1. **Implement Pareto-improving re-optimisation** and benchmark it on the same three profiles.
2. **Tune `aging_threshold` empirically** with a sensitivity sweep — the analytic default is defensible but the optimum is profile-dependent.
3. **Event-driven simulation mode** that skips idle ticks, while keeping the tick-based mode for parity with the spec.
4. **Property-based tests** for no-starvation under arbitrary input.
5. **Animated visualization** of elevator movement against the per-tick log.
