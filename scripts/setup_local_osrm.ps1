$ErrorActionPreference = "Stop"

$dataDirectory = Join-Path $PSScriptRoot "..\data\osrm"
$pbfPath = Join-Path $dataDirectory "us-latest.osm.pbf"
New-Item -ItemType Directory -Force -Path $dataDirectory | Out-Null

if (-not (Test-Path $pbfPath)) {
    Invoke-WebRequest `
        -Uri "https://download.geofabrik.de/north-america/us-latest.osm.pbf" `
        -OutFile $pbfPath
}

$mount = "${dataDirectory}:/data"
docker run --rm -t -v $mount osrm/osrm-backend:v5.27.1 `
    osrm-extract -p /opt/car.lua /data/us-latest.osm.pbf
docker run --rm -t -v $mount osrm/osrm-backend:v5.27.1 `
    osrm-partition /data/us-latest.osrm
docker run --rm -t -v $mount osrm/osrm-backend:v5.27.1 `
    osrm-customize /data/us-latest.osrm

docker compose up --build -d
