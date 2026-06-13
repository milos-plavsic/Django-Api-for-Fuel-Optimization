from django.shortcuts import render
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .services import FuelOptimizationService

class IndexView(View):
    def get(self, request):
        return render(request, 'index.html')

class RouteOptimizationView(APIView):
    def get(self, request):
        start = request.query_params.get('start')
        finish = request.query_params.get('finish')

        if not start or not finish:
            return Response(
                {"error": "Please provide 'start' and 'finish' query parameters."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Parse vehicle parameters with sensible defaults
        try:
            mpg = float(request.query_params.get('mpg', 10))
            fuel_capacity = float(request.query_params.get('fuel_capacity', 50))
            current_fuel = float(request.query_params.get('current_fuel', 50))
            safety_reserve = float(request.query_params.get('safety_reserve', 0.1))
        except (TypeError, ValueError):
            return Response(
                {"error": "Invalid numeric parameters for mpg, fuel_capacity, current_fuel, or safety_reserve."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            geometry, total_distance = FuelOptimizationService.get_route(start, finish)
            route_coords = geometry['coordinates']
            
            stops, total_cost, total_detour, strategy = FuelOptimizationService.optimize_fuel_plan(
                route_coords, total_distance, 
                mpg=mpg, 
                fuel_capacity=fuel_capacity, 
                current_fuel=current_fuel, 
                safety_reserve_pct=safety_reserve
            )
            
            return Response({
                "route": geometry,
                "total_distance_miles": total_distance,
                "total_detour_miles": total_detour,
                "number_of_stops": len(stops),
                "fuel_stops": stops,
                "total_fuel_cost": total_cost,
                "strategy_used": strategy,
                "vehicle_profile": {
                    "mpg": mpg,
                    "fuel_capacity": fuel_capacity,
                    "current_fuel": current_fuel,
                    "safety_reserve": safety_reserve
                }
            }, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": "An error occurred during route optimization."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
