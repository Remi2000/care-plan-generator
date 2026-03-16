from django.shortcuts import render
from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .serializers import CreateOrderSerializer

from .services import (
    create_order_service,
    get_order_service,
    search_orders_service,
    get_care_plan_content,
    get_careplan_status_service,
)


def index(request):
    return render(request, "orders/index.html")


@api_view(["POST"])
def create_order(request):
    print("===== [views.py] 收到请求 =====")
    print(f"request.data: {request.data}")

    # 新增：交给serializer整理数据
    serializer = CreateOrderSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    print("===== [serializers.py] 数据验证通过 =====")
    print(f"validated_data: {serializer.validated_data}")

    # 把整理好的数据交给service
    order, care_plan, warnings = create_order_service(serializer.validated_data)
    print("===== [views.py] service执行完毕 =====")

    return Response({
        "order_id":    order.id,
        "careplan_id": care_plan.id,
        "status":      "pending",
        "warnings":    warnings,
    }, status=201)


@api_view(["GET"])
def get_order(request, pk):
    result = get_order_service(pk)
    if result is None:
        return Response({"error": "Order not found"}, status=404)
    return Response(result)


@api_view(["GET"])
def search_orders(request):
    q = request.query_params.get("q", "")
    results = search_orders_service(q)
    return Response(results)


@api_view(["GET"])
def download_care_plan(request, pk):
    order, result = get_care_plan_content(pk)
    if order is None:
        status_code = 404 if result in ("Order not found", "Care plan not found") else 400
        return HttpResponse(result, status=status_code)

    response = HttpResponse(result, content_type="text/plain")
    response["Content-Disposition"] = f"attachment; filename=care_plan_order_{order.id}.txt"
    return response


@api_view(["GET"])
def get_careplan_status(request, careplan_id):
    result = get_careplan_status_service(careplan_id)
    if result is None:
        return Response({"error": "CarePlan not found"}, status=404)
    return Response(result)