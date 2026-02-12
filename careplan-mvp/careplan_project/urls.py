from django.urls import path, include
from orders.views import index

urlpatterns = [
    path("", index, name="index"),
    path("api/", include("orders.urls")),
]