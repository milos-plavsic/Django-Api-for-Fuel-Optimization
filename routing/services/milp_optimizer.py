import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from .optimizer import (
    EPSILON,
    MAX_RANGE_MILES,
    MPG,
    TANK_GALLONS,
    Node,
    NoFeasibleFuelPlan,
    _reachable_to_destination,
    _validate_station_chain,
)


def optimize_fuel_stops_milp(stations, total_distance):
    nodes = [Node(0.0, 0.0, None, None)]
    nodes.extend(
        Node(s["route_mile"], s["detour_miles"], s["price_per_gallon"], s)
        for s in stations
        if EPSILON < s["route_mile"] < total_distance - EPSILON
    )
    nodes.append(Node(total_distance, 0.0, 0.0, None))
    _validate_station_chain(nodes, _reachable_to_destination(nodes))
    station_nodes = nodes[1:-1]
    count = len(station_nodes)
    if count == 0:
        return _empty_plan(total_distance)

    purchase_offset = 0
    used_offset = count
    fuel_offset = count * 2
    variable_count = count * 3
    objective = np.zeros(variable_count)
    objective[purchase_offset:used_offset] = [node.price for node in station_nodes]
    integrality = np.zeros(variable_count)
    integrality[used_offset:fuel_offset] = 1
    lower = np.zeros(variable_count)
    upper = np.full(variable_count, TANK_GALLONS)
    upper[used_offset:fuel_offset] = 1
    constraints = []

    balance = lil_matrix((count, variable_count))
    balance_rhs = np.zeros(count)
    previous_mile = 0.0
    for index, node in enumerate(station_nodes):
        route_fuel = (node.route_mile - previous_mile) / MPG
        detour_fuel = 2 * node.detour_miles / MPG
        balance[index, fuel_offset + index] = 1
        balance[index, purchase_offset + index] = -1
        balance[index, used_offset + index] = detour_fuel
        if index == 0:
            balance_rhs[index] = TANK_GALLONS - route_fuel
        else:
            balance[index, fuel_offset + index - 1] = -1
            balance_rhs[index] = -route_fuel
        previous_mile = node.route_mile
    constraints.append(LinearConstraint(balance.tocsr(), balance_rhs, balance_rhs))

    purchase_link = lil_matrix((count, variable_count))
    for index in range(count):
        purchase_link[index, purchase_offset + index] = 1
        purchase_link[index, used_offset + index] = -TANK_GALLONS
    constraints.append(
        LinearConstraint(purchase_link.tocsr(), np.full(count, -np.inf), np.zeros(count))
    )

    capacity = lil_matrix((count, variable_count))
    capacity_upper = np.zeros(count)
    previous_mile = 0.0
    for index, node in enumerate(station_nodes):
        route_fuel = (node.route_mile - previous_mile) / MPG
        outbound_fuel = node.detour_miles / MPG
        capacity[index, purchase_offset + index] = 1
        capacity[index, used_offset + index] = -outbound_fuel
        if index == 0:
            capacity_upper[index] = route_fuel
        else:
            capacity[index, fuel_offset + index - 1] = 1
            capacity_upper[index] = TANK_GALLONS + route_fuel
        previous_mile = node.route_mile
    constraints.append(
        LinearConstraint(capacity.tocsr(), np.full(count, -np.inf), capacity_upper)
    )

    arrival = lil_matrix((count, variable_count))
    arrival_lower = np.zeros(count)
    previous_mile = 0.0
    for index, node in enumerate(station_nodes):
        route_fuel = (node.route_mile - previous_mile) / MPG
        outbound_fuel = node.detour_miles / MPG
        arrival[index, used_offset + index] = -outbound_fuel
        if index == 0:
            arrival_lower[index] = route_fuel - TANK_GALLONS
        else:
            arrival[index, fuel_offset + index - 1] = 1
            arrival_lower[index] = route_fuel
        previous_mile = node.route_mile
    constraints.append(
        LinearConstraint(arrival.tocsr(), arrival_lower, np.full(count, np.inf))
    )

    destination_fuel = (total_distance - station_nodes[-1].route_mile) / MPG
    destination = lil_matrix((1, variable_count))
    destination[0, fuel_offset + count - 1] = 1
    constraints.append(
        LinearConstraint(destination.tocsr(), [destination_fuel], [np.inf])
    )

    result = milp(
        objective,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints,
        options={"time_limit": 15.0, "mip_rel_gap": 1e-8},
    )
    if result.x is None:
        raise NoFeasibleFuelPlan(f"No optimal fuel purchase plan was found: {result.message}")

    purchases = []
    detour_fuel = 0.0
    for node, gallons, used in zip(
        station_nodes,
        result.x[purchase_offset:used_offset],
        result.x[used_offset:fuel_offset],
    ):
        if used > 0.5 and gallons > 0.01:
            station = dict(node.station)
            station["gallons_purchased"] = round(float(gallons), 3)
            station["purchase_cost"] = round(float(gallons) * node.price, 2)
            purchases.append(station)
            detour_fuel += 2 * node.detour_miles / MPG

    total_cost = round(sum(stop["purchase_cost"] for stop in purchases), 2)
    return {
        "fuel_stops": purchases,
        "total_fuel_cost": total_cost,
        "trip_fuel_consumed_gallons": round(total_distance / MPG + detour_fuel, 3),
        "starting_fuel_gallons": TANK_GALLONS,
        "ending_fuel_gallons": round(float(result.x[-1] - destination_fuel), 3),
        "maximum_range_miles": MAX_RANGE_MILES,
        "miles_per_gallon": MPG,
        "optimization_objective_cost": total_cost,
        "optimization_optimality_proven": bool(result.success),
        "optimization_mip_gap": round(float(getattr(result, "mip_gap", 0.0)), 6),
        "optimization_method": "milp_fuel_price",
    }


def _empty_plan(total_distance):
    return {
        "fuel_stops": [],
        "total_fuel_cost": 0.0,
        "trip_fuel_consumed_gallons": round(total_distance / MPG, 3),
        "starting_fuel_gallons": TANK_GALLONS,
        "ending_fuel_gallons": round(TANK_GALLONS - total_distance / MPG, 3),
        "maximum_range_miles": MAX_RANGE_MILES,
        "miles_per_gallon": MPG,
        "optimization_objective_cost": 0.0,
        "optimization_optimality_proven": True,
        "optimization_mip_gap": 0.0,
        "optimization_method": "milp_fuel_price",
    }
