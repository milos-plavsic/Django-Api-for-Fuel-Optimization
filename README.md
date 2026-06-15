# Fuel Route Optimization API

A Django REST API that resolves US locations locally, makes at most one external
routing request, and calculates cost-effective fuel purchases along the route.

## Solution Design

- Text locations and postal codes are resolved from the local `Location` table.
- Coordinate inputs are validated against US geographic bounds.
- OSRM is called once for an uncached route and never for geocoding or fuel stops.
- Fuel stations are selected and projected onto the route locally.
- The feasibility-aware route optimizer assumes exactly 500 miles maximum
  range, 10 MPG, and a full 50-gallon tank at departure.
- Optimization selects only stops that can continue to the destination, then
  chooses the cheapest reachable viable station. Fuel purchases follow the
  standard rule of buying enough to reach a cheaper next stop or filling the
  tank when the next stop is more expensive.
- When only the primary OSRM route is evaluated - latency is minimized.
- The objective is purchased-fuel cost only. Initial-tank fuel is excluded.
- `total_fuel_cost` includes purchases made during the route. The initial
  full tank has no supplied origin price and is therefore reported separately.

## Server Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py import_us_postal_codes US.txt
python manage.py import_stations fuel-prices-for-be-assessment.csv
python manage.py runserver
```

Open `http://127.0.0.1:8000/` for the Leaflet route-planning interface.

## Two solutions

Solutions use local geocoding, the same fuel-price dataset, 500-mile range,
10 MPG, and the fuel-price optimizer.

| Endpoint                | Routes evaluated         | Routing calls | Selection objective              |

| `POST /api/route/`      | User-selected 1-5 routes | One OSRM call | Fast Purchased fuel cost         |
| `POST /api/route-milp/` | User-selected 1-5 routes | One OSRM call | MILP minimum purchased-fuel cost |

Every solution evaluates every route OSRM returns and fails only after all
returned routes are infeasible. Send `route_count` from `1` to `5`. OSRM may
return fewer alternatives than requested and does not enumerate every possible
road route. For route counts above one, the single OSRM call requests all
alternatives the provider can produce, then the API evaluates returned routes up
to the selected limit.

Unknown local text, malformed coordinates, locations outside the USA, missing
station chains, and routing-provider failures return explicit non-200 responses.

Completed plans are cached separately from route geometry. Cache keys include
resolved coordinates, optimization settings, algorithm version, and the latest
fuel-station update timestamp, so station imports automatically invalidate stale
plans. Using a shared Redis cache with multiple production workers.
