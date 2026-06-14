from dataclasses import dataclass

MAX_RANGE_MILES = 500.0
MPG = 10.0
TANK_GALLONS = MAX_RANGE_MILES / MPG
EPSILON = 1e-6


class NoFeasibleFuelPlan(Exception):
    def __init__(self, message, *, last_reachable_mile=None, next_available_mile=None):
        super().__init__(message)
        self.last_reachable_mile = last_reachable_mile
        self.next_available_mile = next_available_mile

    @property
    def gap_miles(self):
        if self.last_reachable_mile is None or self.next_available_mile is None:
            return None
        return self.next_available_mile - self.last_reachable_mile


@dataclass
class Node:
    route_mile: float
    detour_miles: float
    price: float | None
    station: dict | None


def travel_distance(first, second):
    return (
        second.route_mile
        - first.route_mile
        + first.detour_miles
        + second.detour_miles
    )


def _reachable_to_destination(nodes):
    viable = {len(nodes) - 1}
    for index in range(len(nodes) - 2, -1, -1):
        if any(
            travel_distance(nodes[index], nodes[next_index]) <= MAX_RANGE_MILES + EPSILON
            for next_index in viable
            if next_index > index
        ):
            viable.add(index)
    return viable


def _validate_station_chain(nodes, viable):
    if 0 in viable:
        return

    reachable = {0}
    for index in range(1, len(nodes)):
        if any(
            travel_distance(nodes[previous], nodes[index]) <= MAX_RANGE_MILES + EPSILON
            for previous in reachable
        ):
            reachable.add(index)
    last_index = max(reachable, key=lambda index: nodes[index].route_mile)
    next_index = min(
        range(last_index + 1, len(nodes)),
        key=lambda index: nodes[index].route_mile,
    )
    raise NoFeasibleFuelPlan(
        (
            "The supplied fuel-price dataset has no reachable station chain. "
            f"The last reachable priced station is near route mile "
            f"{nodes[last_index].route_mile:.1f}, and the next priced stop or "
            f"destination is near mile {nodes[next_index].route_mile:.1f}."
        ),
        last_reachable_mile=nodes[last_index].route_mile,
        next_available_mile=nodes[next_index].route_mile,
    )


def _next_stop(nodes, current_index, viable, available_miles):
    destination_index = len(nodes) - 1
    reachable = [
        index
        for index in range(current_index + 1, len(nodes))
        if index in viable
        and travel_distance(nodes[current_index], nodes[index]) <= available_miles + EPSILON
    ]
    if not reachable:
        return None

    reachable_stations = [
        index for index in reachable if index != destination_index
    ]
    cheapest_station = min(
        reachable_stations,
        key=lambda index: (
            nodes[index].price,
            -nodes[index].route_mile,
            nodes[index].detour_miles,
        ),
        default=None,
    )
    current_price = nodes[current_index].price
    if destination_index in reachable and (
        current_price is None
        or cheapest_station is None
        or nodes[cheapest_station].price >= current_price - EPSILON
    ):
        return destination_index
    return cheapest_station


def optimize_fuel_stops(stations, total_distance):
    nodes = [Node(0.0, 0.0, None, None)]
    nodes.extend(
        Node(s["route_mile"], s["detour_miles"], s["price_per_gallon"], s)
        for s in stations
        if EPSILON < s["route_mile"] < total_distance - EPSILON
    )
    nodes.append(Node(total_distance, 0.0, 0.0, None))

    viable = _reachable_to_destination(nodes)
    _validate_station_chain(nodes, viable)

    purchases = []
    current_index = 0
    fuel = TANK_GALLONS
    detour_fuel = 0.0
    while current_index != len(nodes) - 1:
        current = nodes[current_index]
        available_miles = fuel * MPG if current.station is None else MAX_RANGE_MILES
        next_index = _next_stop(nodes, current_index, viable, available_miles)
        if next_index is None:
            raise NoFeasibleFuelPlan("No feasible fuel stop can continue this route.")

        distance = travel_distance(nodes[current_index], nodes[next_index])
        required_gallons = distance / MPG
        if current.station is not None:
            next_node = nodes[next_index]
            target_fuel = (
                required_gallons
                if next_node.station is None or next_node.price < current.price - EPSILON
                else TANK_GALLONS
            )
            gallons = max(0.0, target_fuel - fuel)
        else:
            gallons = 0.0

        if gallons > EPSILON:
            station = dict(current.station)
            station["gallons_purchased"] = round(gallons, 3)
            station["purchase_cost"] = round(gallons * current.price, 2)
            purchases.append(station)
            fuel += gallons

        fuel -= required_gallons
        if nodes[next_index].station is not None:
            detour_fuel += 2 * nodes[next_index].detour_miles / MPG
        current_index = next_index

    total_fuel_cost = round(sum(stop["purchase_cost"] for stop in purchases), 2)
    return {
        "fuel_stops": purchases,
        "total_fuel_cost": total_fuel_cost,
        "trip_fuel_consumed_gallons": round(total_distance / MPG + detour_fuel, 3),
        "starting_fuel_gallons": TANK_GALLONS,
        "ending_fuel_gallons": round(fuel, 3),
        "maximum_range_miles": MAX_RANGE_MILES,
        "miles_per_gallon": MPG,
        "optimization_objective_cost": total_fuel_cost,
        "optimization_optimality_proven": False,
        "optimization_mip_gap": None,
        "optimization_method": "fuel_price_greedy",
    }
