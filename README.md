# Fuel Route Optimization API

A Django REST API that resolves US locations locally, makes at most one external
routing request, and calculates cost-effective fuel purchases along the route.

## Design

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
- Only the primary OSRM route is evaluated. This minimizes latency and keeps the
  runtime routing requirement to one call.
- The objective is purchased-fuel cost only. Initial-tank fuel is excluded.
- `total_fuel_cost` includes purchases made during the route. The initial
  full tank has no supplied origin price and is therefore reported separately.

## Setup

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

## Three solutions

All solutions use local geocoding, the same fuel-price dataset, 500-mile range,
10 MPG, and the millisecond fuel-price optimizer.

| Endpoint | Routes evaluated | Routing calls | Selection objective |
|---|---:|---:|---|
| `POST /api/route/` | Primary route, or first feasible fallback alternative | One OSRM call | Purchased fuel cost |
| `POST /api/route-alternative/` | Primary plus up to one alternative | One OSRM call | Purchased fuel cost |
| `POST /api/route-three/` | Primary plus up to two alternatives | One OSRM call | Purchased fuel cost |
| `POST /api/route-milp/` | Primary route, or first feasible fallback | One OSRM call | MILP minimum purchased-fuel cost |

OSRM may return fewer alternatives than requested.

## Postman demonstration

Start the API, create a new Postman HTTP request, and configure:

- Method: `POST`
- URL: `http://127.0.0.1:8000/api/route/`
- Header: `Content-Type: application/json`
- Body: select **raw**, then **JSON**

Text/postal example:

```json
{
  "start": "12345",
  "finish": "Santa Barbara, CA"
}
```

Coordinate example:

```json
{
  "start": {"latitude": 40.7128, "longitude": -74.0060},
  "finish": {"latitude": 34.0522, "longitude": -118.2437}
}
```

Click **Send**. A successful response is HTTP `200` and includes the resolved
locations, simplified route GeoJSON, distance, fuel stops, and total fuel cost.
Demonstrate validation by sending an unknown place or coordinates outside the
USA; the API returns an explicit HTTP `400` response without calling OSRM.

Alternatively, import
`postman/Fuel Route Optimization API.postman_collection.json` into Postman.
It includes successful text, coordinate, and invalid-input demonstrations.

The same request can be demonstrated with curl:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/route/ `
  -H "Content-Type: application/json" `
  -d "{\"start\":\"12345\",\"finish\":\"Santa Barbara, CA\"}"
```

The original assessment fuel-price CSV has no coordinates. After importing the
US postal dataset, `import_stations` resolves those rows locally by city/state:

```powershell
python manage.py import_stations fuel-prices-for-be-assessment.csv
```

This preserves the one-call runtime design. City-level coordinates are suitable
as an explicit fallback. For better locations, import an offline highway-junction
CSV and re-run the station import:

```powershell
python manage.py import_highway_junctions highway_junctions.csv
python manage.py import_stations fuel-prices-for-be-assessment.csv
```

The junction CSV requires `state`, `highway`, `exit_number`, `latitude`, and
`longitude`. It may contain `name`. Runtime still performs only one route call.

OpenStreetMap junctions can also be fetched in resumable state-level batches:

```powershell
python manage.py fetch_osm_highway_junctions
python manage.py import_stations fuel-prices-for-be-assessment.csv
```

Fetched Overpass responses are cached under `data/overpass`, so interrupted
imports resume without repeating completed state requests.

Station responses expose `location_source` and `location_confidence`:

- `osm_highway_exit` (`0.95`): named highway and exit decoded from OSM.
- `osm_highway_near_city` (`0.60`-`0.75`): named highway/intersection nearest the supplied city.
- `city_centroid` (`0.35`): explicit fallback where the description cannot be resolved safely.

For additional local text coverage, import a US geocoding dataset:

```powershell
python manage.py import_locations us_locations.csv
```

`us_locations.csv` must contain `text`, `latitude`, and `longitude`. It may also
contain `display_name`, `kind`, and `state`.

GeoNames postal data can be imported directly from its extracted `US.txt` file:

```powershell
python manage.py import_us_postal_codes US.txt
```

Postal inputs accept `12345`, `NY 12345`, and ZIP+4 forms. A state that does not
match the postal code is rejected before routing. If a five-digit ZIP has
multiple local records, a bare ZIP is rejected as ambiguous; a state prefix is
used to disambiguate when it identifies exactly one record.

Bare city names are accepted when they identify exactly one city/state in the
local place index. Ambiguous names such as `Springfield` are rejected with
candidate states; use `Springfield, MO` to disambiguate. When one city/state has
at least three times the local postal coverage of every alternative, it is
treated as the dominant interpretation, so common inputs such as `Bakersfield`
resolve to California.

## Production stack

The Docker Compose stack runs Gunicorn, Redis shared caching, and a private OSRM
service. Prepare the local US OSRM graph once, then start the stack:

```powershell
.\scripts\setup_local_osrm.ps1
```

Preparing the nationwide graph downloads several gigabytes and requires
substantial temporary disk and memory. Run preparation on production-class
hardware. After it completes, normal API requests make one fast call to the
local OSRM container. Redis shares completed-plan and route caches across
Gunicorn workers and preserves useful cached entries across API restarts.

The full OSRM geometry is retained internally for accurate station matching.
Responses return a simplified route capped at 1,000 points, substantially
reducing JSON serialization, transfer size, and browser map-rendering work.

## Request

```http
POST /api/route/
Content-Type: application/json

{
  "start": "New York, NY",
  "finish": "19103"
}
```

Coordinates are also accepted:

```json
{
  "start": {"latitude": 40.7128, "longitude": -74.0060},
  "finish": {"latitude": 34.0522, "longitude": -118.2437}
}
```

Unknown local text, malformed coordinates, locations outside the USA, missing
station chains, and routing-provider failures return explicit non-200 responses.

Completed plans are cached separately from route geometry. Cache keys include
resolved coordinates, optimization settings, algorithm version, and the latest
fuel-station update timestamp, so station imports automatically invalidate stale
plans. Use a shared Redis cache with multiple production workers.
