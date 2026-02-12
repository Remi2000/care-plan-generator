import anthropic
from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Patient, Provider, Order


def index(request):
    return render(request, "orders/index.html")


@api_view(["POST"])
def create_order(request):
    data = request.data

    patient, _ = Patient.objects.get_or_create(
        mrn=data["mrn"],
        defaults={
            "first_name": data["patient_first_name"],
            "last_name": data["patient_last_name"],
            "diagnosis": data.get("diagnosis", ""),
            "medical_history": data.get("medical_history", ""),
        },
    )

    provider, _ = Provider.objects.get_or_create(
        npi=data["npi"],
        defaults={
            "first_name": data["provider_first_name"],
            "last_name": data["provider_last_name"],
        },
    )

    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication=data["medication"],
        status="pending",
    )

    order.status = "processing"
    order.save()

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = (
            "You are a clinical pharmacist. Generate a care plan for this patient.\n\n"
            f"Patient: {patient.first_name} {patient.last_name}\n"
            f"MRN: {patient.mrn}\n"
            f"Diagnosis: {patient.diagnosis}\n"
            f"Medical History: {patient.medical_history}\n"
            f"Medication: {order.medication}\n"
            f"Provider: Dr. {provider.first_name} {provider.last_name} (NPI: {provider.npi})\n\n"
            "Please generate a care plan that includes:\n"
            "1. Medication review\n"
            "2. Monitoring parameters\n"
            "3. Patient education points\n"
            "4. Follow-up recommendations"
        )

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        order.care_plan = message.content[0].text
        order.status = "completed"
        order.save()

    except Exception as e:
        order.status = "failed"
        order.care_plan = str(e)
        order.save()

    return Response({"order_id": order.id, "status": order.status}, status=201)


@api_view(["GET"])
def get_order(request, pk):
    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return Response({"error": "Order not found"}, status=404)

    result = {
        "order_id": order.id,
        "status": order.status,
        "patient": f"{order.patient.first_name} {order.patient.last_name}",
        "provider": f"Dr. {order.provider.first_name} {order.provider.last_name}",
        "medication": order.medication,
        "created_at": order.created_at,
    }

    if order.status == "completed":
        result["care_plan"] = order.care_plan

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
        results.append({
            "order_id": order.id,
            "status": order.status,
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

    if order.status != "completed":
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
        f"{order.care_plan}\n"
    )

    response = HttpResponse(content, content_type="text/plain")
    response["Content-Disposition"] = f"attachment; filename=care_plan_order_{order.id}.txt"
    return response