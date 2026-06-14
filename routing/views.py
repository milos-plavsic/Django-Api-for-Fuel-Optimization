from django.conf import settings
from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RouteRequestSerializer
from .services.geo import simplify_route
from .services.milp_optimizer import optimize_fuel_stops_milp
from .services.optimizer import NoFeasibleFuelPlan, optimize_fuel_stops
from .services.osrm import RoutingProviderError, get_routes
from .services.plan_cache import cache_plan, get_cached_plan, plan_cache_key
from .services.resolver import resolve_location
from .services.stations import stations_along_route


class IndexView(TemplateView):
    template_name = "routing/index.html"


class RouteOptimizationView(APIView):
    solution_name = "primary"
    max_routes = 2
    include_tolls = False
    stop_after_first_feasible = True

    def get_candidate_routes(self, start, finish):
        return get_routes(start, finish, max_routes=self.max_routes)

    def selection_cost(self, route, plan):
        return plan["total_fuel_cost"]

    def optimize(self, stations, distance_miles):
        return optimize_fuel_stops(stations, distance_miles)

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        start = resolve_location(serializer.validated_data["start"])
        finish = resolve_location(serializer.validated_data["finish"])

        completed_plan_key = plan_cache_key(
            start["coordinates"],
            finish["coordinates"],
            solution=self.solution_name,
        )
        cached_result = get_cached_plan(completed_plan_key)
        if cached_result is not None:
            return Response({**cached_result, "routing_api_calls": 0})

        route = None
        stations = []
        try:
            routes, external_calls = self.get_candidate_routes(
                start["coordinates"],
                finish["coordinates"],
            )
            candidates = []
            last_plan_error = None
            routes_evaluated = 0
            for route_index, candidate_route in enumerate(routes):
                routes_evaluated += 1
                candidate_stations = stations_along_route(
                    candidate_route["geometry"],
                    candidate_route["distance_miles"],
                )
                try:
                    plan = self.optimize(
                        candidate_stations,
                        candidate_route["distance_miles"],
                    )
                except NoFeasibleFuelPlan as exc:
                    last_plan_error = exc
                    continue
                candidates.append(
                    {
                        "route_index": route_index,
                        "route": candidate_route,
                        "stations": candidate_stations,
                        "plan": plan,
                        "selection_cost": self.selection_cost(candidate_route, plan),
                    }
                )
                if self.stop_after_first_feasible:
                    break
            if not candidates:
                raise last_plan_error or NoFeasibleFuelPlan(
                    "No priced station chain can cover any returned route."
                )
            selected = min(candidates, key=lambda candidate: candidate["selection_cost"])
            route = selected["route"]
            stations = selected["stations"]
            plan = selected["plan"]
        except RoutingProviderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except NoFeasibleFuelPlan as exc:
            return Response(
                {
                    "detail": str(exc),
                    "reason": "insufficient_fuel_price_coverage",
                    "distance_miles": (
                        round(route["distance_miles"], 2) if route is not None else None
                    ),
                    "priced_stations_near_route": len(stations),
                    "last_reachable_mile": exc.last_reachable_mile,
                    "next_available_mile": exc.next_available_mile,
                    "uncovered_gap_miles": (
                        round(exc.gap_miles, 2) if exc.gap_miles is not None else None
                    ),
                    "maximum_range_miles": 500.0,
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        result = {
            "solution": self.solution_name,
            "start": start,
            "finish": finish,
            "route": {
                "type": "LineString",
                "coordinates": simplify_route(
                    route["geometry"]["coordinates"],
                    tolerance=settings.RESPONSE_ROUTE_SIMPLIFY_TOLERANCE,
                    max_points=settings.RESPONSE_ROUTE_MAX_POINTS,
                ),
            },
            "distance_miles": round(route["distance_miles"], 2),
            "duration_seconds": route["duration_seconds"],
            **plan,
            "routes_evaluated": routes_evaluated,
            "selected_route_index": selected["route_index"],
            "routing_api_calls": external_calls,
        }
        cache_plan(completed_plan_key, result)
        return Response(result)


class AlternativeRouteOptimizationView(RouteOptimizationView):
    solution_name = "two_routes"
    max_routes = 2
    stop_after_first_feasible = False


class ThreeRouteOptimizationView(RouteOptimizationView):
    solution_name = "three_routes"
    max_routes = 3
    stop_after_first_feasible = False


class MilpRouteOptimizationView(RouteOptimizationView):
    solution_name = "milp_optimal"

    def optimize(self, stations, distance_miles):
        return optimize_fuel_stops_milp(stations, distance_miles)
