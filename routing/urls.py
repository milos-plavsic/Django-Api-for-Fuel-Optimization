from django.urls import path

from .views import (
    AlternativeRouteOptimizationView,
    MilpRouteOptimizationView,
    RouteOptimizationView,
    ThreeRouteOptimizationView,
)


urlpatterns = [
    path("route/", RouteOptimizationView.as_view(), name="route-optimization"),
    path(
        "route-alternative/",
        AlternativeRouteOptimizationView.as_view(),
        name="route-alternative-optimization",
    ),
    path(
        "route-three/",
        ThreeRouteOptimizationView.as_view(),
        name="route-three-optimization",
    ),
    path("route-milp/", MilpRouteOptimizationView.as_view(), name="route-milp-optimization"),
]
