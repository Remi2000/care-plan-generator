from django.urls import path
from . import views

urlpatterns = [
    path("orders/", views.create_order, name="create_order"),
    path("orders/<int:pk>/", views.get_order, name="get_order"),
    path("orders/search/", views.search_orders, name="search_orders"),
    path("orders/<int:pk>/download/", views.download_care_plan, name="download_care_plan"),
]
