from django.urls import include, path

from routing.views import IndexView


urlpatterns = [
    path("", IndexView.as_view(), name="index"),
    path("api/", include("routing.urls")),
]
