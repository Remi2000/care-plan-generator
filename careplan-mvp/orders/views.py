import redis
import json
import anthropic
from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Patient, Provider, Order, CarePlan


def index(request):
    return render(request, "orders/index.html")


@api_view(["POST"])
def create_order(request):
    data = request.data
    print("===== STEP 1: 收到前端的数据 =====")
    print(data)

    patient, _ = Patient.objects.get_or_create(
        mrn=data["mrn"],
        defaults={
            "first_name": data["patient_first_name"],
            "last_name": data["patient_last_name"],
        },
    )
    print("===== STEP 2: 患者信息 =====")
    print(f"Patient: {patient.first_name} {patient.last_name}")

    provider, _ = Provider.objects.get_or_create(
        npi=data["npi"],
        defaults={
            "first_name": data["provider_first_name"],
            "last_name": data["provider_last_name"],
        },
    )
    print("===== STEP 3: Provider信息 =====")
    print(f"Provider: {provider.first_name} {provider.last_name}")

    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication=data["medication"],
        diagnosis=data.get("diagnosis", ""),
        medical_history=data.get("medical_history", ""),
    )
    print("===== STEP 4: 订单已创建 =====")
    print(f"Order ID: {order.id}")

    # 第一步：先存数据库，status=pending
    care_plan = CarePlan.objects.create(
        order=order,
        status="pending",
    )
    print("===== STEP 5: CarePlan 已存数据库, status=pending =====")

    # 第二步：把任务交给 Celery 异步处理
    # .delay() 就是"丢给 Celery，不等结果，立刻返回"
    from orders.tasks import generate_care_plan
    generate_care_plan.delay(care_plan.id)
    print(f"===== STEP 6: careplan_id={care_plan.id} 已交给 Celery =====")

    # 第三步：立刻返回，不等Claude
    print("===== STEP 7: 立刻返回给前端 =====")
    return Response({"order_id": order.id, "careplan_id": care_plan.id, "status": "pending"}, status=201)


@api_view(["GET"])
def get_order(request, pk):
    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return Response({"error": "Order not found"}, status=404)

    result = {
        "order_id": order.id,
        "patient": f"{order.patient.first_name} {order.patient.last_name}",
        "provider": f"Dr. {order.provider.first_name} {order.provider.last_name}",
        "medication": order.medication,
        "created_at": order.created_at,
    }

    # Get the care plan for this order
    try:
        care_plan = order.careplan
        result["status"] = care_plan.status
        if care_plan.status == "completed":
            result["care_plan"] = care_plan.content
    except CarePlan.DoesNotExist:
        result["status"] = "no care plan"

    return Response(result)


@api_view(["GET"])
def search_orders(request):
    q = request.query_params.get("q", "")
    orders = Order.objects.filter(
        patient__first_name__icontains=q
    ) | Order.objects.filter(
        patient__last_name__icontains=q
    ) | Order.objects.filter(
        patient__mrn__icontains=q
    )

    results = []
    for order in orders:
        # Get care plan status
        try:
            status = order.careplan.status
        except CarePlan.DoesNotExist:
            status = "no care plan"

        results.append({
            "order_id": order.id,
            "status": status,
            "patient": f"{order.patient.first_name} {order.patient.last_name}",
            "mrn": order.patient.mrn,
            "medication": order.medication,
            "created_at": order.created_at,
        })

    return Response(results)


@api_view(["GET"])
def download_care_plan(request, pk):
    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return HttpResponse("Order not found", status=404)

    try:
        care_plan = order.careplan
    except CarePlan.DoesNotExist:
        return HttpResponse("Care plan not found", status=404)

    if care_plan.status != "completed":
        return HttpResponse("Care plan not ready", status=400)

    content = (
        "CARE PLAN\n"
        "========================================\n"
        f"Patient: {order.patient.first_name} {order.patient.last_name}\n"
        f"MRN: {order.patient.mrn}\n"
        f"Provider: Dr. {order.provider.first_name} {order.provider.last_name}\n"
        f"Medication: {order.medication}\n"
        f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        "========================================\n\n"
        f"{care_plan.content}\n"
    )

    response = HttpResponse(content, content_type="text/plain")
    response["Content-Disposition"] = f"attachment; filename=care_plan_order_{order.id}.txt"
    return response