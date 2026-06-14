import json
import re
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from routing.models import FuelStation, HighwayJunction
from routing.services.station_location import normalize_highway


REF_PATTERN = re.compile(r"\b(?P<kind>I|US|SR|ST)\s*-?\s*(?P<number>\d+)\b", re.IGNORECASE)
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


def highways_from_ref(value):
    return {
        normalize_highway(match.group("kind"), match.group("number"))
        for match in REF_PATTERN.finditer(value or "")
    }


class Command(BaseCommand):
    help = "Fetch OSM motorway junctions by state for offline fuel-station geocoding."

    def add_arguments(self, parser):
        parser.add_argument("--states", nargs="*", help="State codes; defaults to imported station states.")
        parser.add_argument("--cache-dir", type=Path, default=settings.BASE_DIR / "data" / "overpass")
        parser.add_argument("--delay", type=float, default=2.0)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        states = options["states"] or list(
            FuelStation.objects.exclude(state="").values_list("state", flat=True).distinct()
        )
        states = sorted(state for state in states if len(state) == 2 and state.isalpha())
        cache_dir = options["cache_dir"]
        cache_dir.mkdir(parents=True, exist_ok=True)
        imported = 0

        for position, state in enumerate(states, start=1):
            cache_path = cache_dir / f"{state}.json"
            if cache_path.exists() and not options["force"]:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
            else:
                query = f"""
                [out:json][timeout:180];
                area["ISO3166-2"="US-{state}"][boundary=administrative]->.state;
                way(area.state)["highway"="motorway"]->.roads;
                node(w.roads)["highway"="motorway_junction"]->.junctions;
                (.roads; .junctions;);
                out body;
                """
                last_error = None
                for attempt in range(6):
                    endpoint = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
                    try:
                        response = requests.post(
                            endpoint,
                            data={"data": query},
                            headers={"User-Agent": "FuelRoutePlanner/1.0 offline-junction-import"},
                            timeout=240,
                        )
                        response.raise_for_status()
                        payload = response.json()
                        break
                    except (requests.RequestException, ValueError) as exc:
                        last_error = exc
                        if attempt < 5:
                            time.sleep(min(60, 5 * (2 ** attempt)))
                else:
                    detail = getattr(locals().get("response"), "text", "")[:500]
                    raise CommandError(
                        f"Could not fetch OSM junctions for {state}: {last_error}. {detail}"
                    ) from last_error
                cache_path.write_text(json.dumps(payload), encoding="utf-8")
                if position < len(states):
                    time.sleep(options["delay"])

            elements = payload.get("elements", [])
            nodes = {
                element["id"]: element
                for element in elements
                if element.get("type") == "node"
                and element.get("tags", {}).get("highway") == "motorway_junction"
                and element.get("tags", {}).get("ref")
            }
            highways_by_node = {node_id: set() for node_id in nodes}
            for element in elements:
                if element.get("type") != "way":
                    continue
                highways = highways_from_ref(element.get("tags", {}).get("ref", ""))
                if not highways:
                    continue
                for node_id in element.get("nodes", []):
                    if node_id in highways_by_node:
                        highways_by_node[node_id].update(highways)

            junctions = []
            for node_id, node in nodes.items():
                tags = node.get("tags", {})
                for highway in highways_by_node[node_id]:
                    junctions.append(
                        HighwayJunction(
                            state=state,
                            highway=highway,
                            exit_number=tags["ref"].upper(),
                            latitude=node["lat"],
                            longitude=node["lon"],
                            name=tags.get("name") or tags.get("exit_to", ""),
                        )
                    )
            HighwayJunction.objects.filter(state=state).delete()
            HighwayJunction.objects.bulk_create(junctions, ignore_conflicts=True, batch_size=1000)
            imported += len(junctions)
            self.stdout.write(f"{state}: imported {len(junctions)} junction/highway matches")

        self.stdout.write(self.style.SUCCESS(f"Imported {imported} junction/highway matches."))
