# Architecture Summary

## Overview

The application is a Django REST API that resolves US locations locally, makes
one routing-provider request, finds priced fuel stations near returned routes,
calculates feasible fuel stops for a vehicle with a 500-mile range, and returns
route GeoJSON, fuel purchases, total fuel cost, and optimization metadata.

It also includes a Leaflet map and a Postman-style browser API tester.

## Technologies And Tools

- Python 3.13
- Django 6.0.6
- Django REST Framework
- OSRM for driving routes and alternatives
- OpenStreetMap and Overpass API for offline highway-junction imports
- GeoNames US postal data for local ZIP and city resolution
- SQLite for local development
- Redis and django-redis for production shared caching
- NumPy for vectorized geographic calculations
- SciPy `cKDTree` for station-to-route spatial matching
- SciPy HiGHS MILP solver for mathematically optimal fuel-price planning
- Leaflet for map rendering
- Postman collection and built-in Postman-style webpage tester
- Requests for OSRM and Overpass HTTP calls
- Gunicorn for production serving
- Docker and Docker Compose
- Git and GitHub

## Runtime Data Flow

```text
Request
-> Validate start and finish
-> Resolve locations locally
-> Check completed-plan cache
-> Make one OSRM routing request
-> Receive requested route alternatives
-> Project priced stations onto every returned route
-> Reject infeasible routes
-> Optimize fuel purchases
-> Select the cheapest feasible result
-> Simplify displayed route geometry
-> Cache completed response
-> Return JSON
```

## Location Resolution Logic

Accepted inputs include coordinates, five-digit ZIP codes, ZIP+4 codes,
state-prefixed ZIP codes, city and state, unique bare city names, and dominant
bare city names.

Logical gates:

1. Coordinates must fall inside broad US geographic bounding boxes.
2. Unknown text inputs are rejected before calling OSRM.
3. Non-unique ZIP codes are rejected unless state information identifies one record.
4. Incorrect ZIP/state combinations are rejected.
5. Bare cities resolve automatically when unique.
6. Ambiguous bare cities resolve only when one candidate has at least three
   times the postal-code coverage of every alternative.
7. Otherwise, the user must provide a state.

## Fuel-Station Location Logic

Station coordinates are assigned using this hierarchy:

1. Provided coordinates: confidence `1.0`.
2. Matching OSM highway and exit: confidence `0.95`.
3. Matching highway near supplied city: confidence `0.60-0.75`.
4. City centroid fallback: confidence `0.35`.
5. Rows without any local match are skipped.

Runtime station gates:

1. Station must fall inside the route bounding box plus a corridor margin.
2. Route geometry is sampled to at most 1,000 points for matching.
3. SciPy `cKDTree` finds the nearest sampled route point.
4. Stations farther than five estimated miles from the route are rejected.
5. Effectively colocated stations are collapsed to the cheapest station.
6. A station is removed when another at the same projected route mile is both
   cheaper and closer.
7. Remaining stations are ordered by projected route mile.

## Shared Vehicle Assumptions

- Maximum range: 500 miles.
- Fuel efficiency: 10 MPG.
- Tank capacity: 50 gallons.
- Vehicle starts with a full tank.
- Initial-tank fuel cost is excluded.
- Fuel prices remain constant.
- Every listed station is open and has unlimited fuel.
- No fuel-grade, truck-access, payment, or availability restrictions exist.
- Detour distance is approximated from station-to-route straight-line distance.
- Actual drivable station detours are not requested from OSRM.

## Feasibility Gates

1. Start, stations, and destination become ordered route nodes.
2. Every transition must remain within 500 miles, including estimated detours.
3. Backward reachability determines which stations can eventually reach the destination.
4. Stations leading to dead ends are excluded.
5. Routes without a complete priced-station chain are rejected.
6. Alternative routes can rescue requests where another route has insufficient
   station coverage.

## Fast Greedy Optimizer

The greedy optimizer runs in milliseconds.

1. Find reachable stations that can eventually reach the destination.
2. Choose the station with the lowest fuel price.
3. Price ties prefer the station farther along the route.
4. Remaining ties prefer the shorter detour.
5. If the next selected station is cheaper, buy only enough fuel to reach it.
6. If the next selected station is more expensive, fill the tank.
7. Drive directly to the destination when reachable and no cheaper useful stop exists.

It is cost-effective but does not prove global optimality.

## MILP Optimizer

The MILP solution uses continuous fuel-purchase variables, binary station-use
variables, fuel-balance constraints, tank-capacity constraints, station-arrival
constraints, destination constraints, and estimated detour fuel consumption.

Its objective is to minimize purchased-fuel cost. It uses a 15-second solver
limit, targets a relative gap of `1e-8`, and reports optimality and remaining gap.

MILP optimality is proven only for the evaluated route and supplied approximate
station locations. It does not prove that OSRM returned every possible road route.
The MILP solver is imported lazily so greedy requests do not pay its startup
memory cost.

## Caching

Two cache layers exist:

1. OSRM route-result cache.
2. Completed-plan cache.

Cache keys include rounded start and finish coordinates, solution variant,
algorithm version, fuel-station data revision, corridor width, vehicle range,
MPG, and response geometry settings.

## Response And UI Decisions

- Full OSRM geometry is used internally.
- Returned geometry is simplified and capped at 1,000 points.
- Leaflet displays routes and stops.
- The built-in API tester displays optimizer, route count, endpoint, request
  JSON, HTTP status, browser-observed latency, and response JSON.
- Users can request one to five routes for either greedy or MILP optimization.
- Every returned route is evaluated; failure is returned only after every route
  supplied by OSRM is infeasible.
- OSRM does not enumerate every possible road route. For any requested count
  above one, the API requests all alternatives available from OSRM and evaluates
  returned routes up to the user's selected limit.
- The Plan cache status is intentionally hidden.

## Error Behavior

- `400`: invalid, unknown, ambiguous, or non-US location.
- `422`: no priced-station chain can cover any returned route.
- `502`: routing provider failure.
- Invalid locations are rejected before OSRM is called.

## Main Limitations

1. Station coordinates are often approximate.
2. Detours use straight-line estimates rather than actual road distance.
3. Route projection uses sampled geometry.
4. OSRM alternatives are not generated based on fuel prices.
5. OSRM may return fewer alternatives than requested.
6. Greedy results are not globally optimal.
7. MILP is optimal only within evaluated routes.
8. Sparse price data can make otherwise drivable routes infeasible.
9. SQLite is not appropriate for high-concurrency production workloads.
10. Toll costs, traffic, station availability, and live fuel prices are excluded.

## Highest-Value Improvements

1. Use exact station coordinates and drivable detours.
2. Evaluate every returned alternative using MILP when optimality matters.
3. Replace SQLite with PostgreSQL/PostGIS.
4. Host OSRM locally.
5. Create a specialized exact dynamic-programming or shortest-path optimizer.
6. Improve sparse fuel-price coverage handling.
7. Add representative benchmark and correctness suites.
8. Remove remaining unused fields and keep documentation synchronized.
