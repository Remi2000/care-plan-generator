from django.utils import timezone
from .models import Patient, Provider, Order, CarePlan
from .exceptions import BlockError, WarningException


def create_order_service(data):
    warnings = []
    confirm = data.get("confirm", False)

    print("===== STEP 1: 收到前端的数据 =====")
    print(data)

    # ── Provider 检测 ──────────────────────────────────────────
    existing_provider = Provider.objects.filter(npi=data["npi"]).first()

    if existing_provider:
        incoming_first = data["provider_first_name"].strip().lower()
        incoming_last  = data["provider_last_name"].strip().lower()
        db_first = existing_provider.first_name.strip().lower()
        db_last  = existing_provider.last_name.strip().lower()

        if incoming_first != db_first or incoming_last != db_last:
            raise BlockError(
                code="DUPLICATE_NPI",
                message="NPI is already registered to a different provider.",
                detail={
                    "npi": data["npi"],
                    "existing": f"{existing_provider.first_name} {existing_provider.last_name}",
                    "incoming": f"{data['provider_first_name']} {data['provider_last_name']}",
                },
            )
        provider = existing_provider
    else:
        provider = Provider.objects.create(
            npi=data["npi"],
            first_name=data["provider_first_name"],
            last_name=data["provider_last_name"],
        )

    print(f"===== STEP 2: Provider → {provider.first_name} {provider.last_name} =====")

    # ── Patient 检测 ───────────────────────────────────────────
    existing_by_mrn = Patient.objects.filter(mrn=data["mrn"]).first()
    existing_by_name_dob = None
    if data.get("dob"):
        existing_by_name_dob = Patient.objects.filter(
            first_name__iexact=data["patient_first_name"],
            last_name__iexact=data["patient_last_name"],
            dob=data["dob"],
        ).exclude(mrn=data["mrn"]).first()

    if existing_by_mrn:
        incoming_first = data["patient_first_name"].strip().lower()
        incoming_last  = data["patient_last_name"].strip().lower()
        db_first = existing_by_mrn.first_name.strip().lower()
        db_last  = existing_by_mrn.last_name.strip().lower()
        name_match = (incoming_first == db_first and incoming_last == db_last)
        incoming_dob = data.get("dob")
        if incoming_dob and existing_by_mrn.dob:
            from datetime import date
            if isinstance(incoming_dob, str):
                incoming_dob = date.fromisoformat(incoming_dob)
            dob_match = (existing_by_mrn.dob == incoming_dob)
        else:
            dob_match = True

        if not name_match or not dob_match:
            warnings.append(WarningException(
                code="PATIENT_DATA_MISMATCH",
                message="MRN already exists but name or DOB differs. Using existing record.",
                detail={
                    "mrn": data["mrn"],
                    "existing": f"{existing_by_mrn.first_name} {existing_by_mrn.last_name}",
                    "incoming": f"{data['patient_first_name']} {data['patient_last_name']}",
                },
            ).to_dict())
        patient = existing_by_mrn

    elif existing_by_name_dob:
        warnings.append(WarningException(
            code="DUPLICATE_PATIENT_DIFFERENT_MRN",
            message="A patient with the same name and DOB exists with a different MRN.",
            detail={
                "existing_mrn": existing_by_name_dob.mrn,
                "incoming_mrn": data["mrn"],
            },
        ).to_dict())
        patient = Patient.objects.create(
            mrn=data["mrn"],
            first_name=data["patient_first_name"],
            last_name=data["patient_last_name"],
            dob=data.get("dob"),
        )
    else:
        patient = Patient.objects.create(
            mrn=data["mrn"],
            first_name=data["patient_first_name"],
            last_name=data["patient_last_name"],
            dob=data.get("dob"),
        )

    print(f"===== STEP 3: Patient → {patient.first_name} {patient.last_name} =====")

    # ── Order 重复检测 ─────────────────────────────────────────
    today = timezone.now().date()

    duplicate_today = Order.objects.filter(
        patient=patient,
        medication=data["medication"],
        created_at__date=today,
    ).first()

    if duplicate_today:
        raise BlockError(
            code="DUPLICATE_ORDER_TODAY",
            message="An order for this patient and medication already exists today.",
            detail={
                "existing_order_id": duplicate_today.id,
                "patient": f"{patient.first_name} {patient.last_name}",
                "medication": data["medication"],
                "date": str(today),
            },
        )

    previous_order = Order.objects.filter(
        patient=patient,
        medication=data["medication"],
    ).exclude(created_at__date=today).first()

    if previous_order and not confirm:
        raise BlockError(
            code="PREVIOUS_ORDER_EXISTS",
            message="A previous order exists for this patient and medication. Pass confirm=true to proceed.",
            detail={
                "existing_order_id": previous_order.id,
                "date": str(previous_order.created_at.date()),
            },
        )
    elif previous_order and confirm:
        warnings.append(WarningException(
            code="PREVIOUS_ORDER_ACKNOWLEDGED",
            message="Proceeding despite existing previous order.",
            detail={"existing_order_id": previous_order.id},
        ).to_dict())

    # ── 创建 Order 和 CarePlan ─────────────────────────────────
    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication=data["medication"],
        diagnosis=data.get("diagnosis", ""),
        medical_history=data.get("medical_history", ""),
    )
    print(f"===== STEP 4: Order ID={order.id} =====")

    care_plan = CarePlan.objects.create(order=order, status="pending")
    print(f"===== STEP 5: CarePlan status=pending =====")

    from orders.tasks import generate_care_plan
    generate_care_plan.delay(care_plan.id)
    print(f"===== STEP 6: careplan_id={care_plan.id} 已交给 Celery =====")

    return order, care_plan, warnings


# 以下函数不变，原样保留
def get_order_service(pk):
    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return None

    result = {
        "order_id": order.id,
        "patient": f"{order.patient.first_name} {order.patient.last_name}",
        "provider": f"Dr. {order.provider.first_name} {order.provider.last_name}",
        "medication": order.medication,
        "created_at": order.created_at,
    }

    try:
        care_plan = order.careplan
        result["status"] = care_plan.status
        if care_plan.status == "completed":
            result["care_plan"] = care_plan.content
    except CarePlan.DoesNotExist:
        result["status"] = "no care plan"

    return result


def search_orders_service(q):
    orders = Order.objects.filter(
        patient__first_name__icontains=q
    ) | Order.objects.filter(
        patient__last_name__icontains=q
    ) | Order.objects.filter(
        patient__mrn__icontains=q
    )

    results = []
    for order in orders:
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

    return results


def get_care_plan_content(pk):
    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return None, "Order not found"

    try:
        care_plan = order.careplan
    except CarePlan.DoesNotExist:
        return None, "Care plan not found"

    if care_plan.status != "completed":
        return None, "Care plan not ready"

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

    return order, content


def get_careplan_status_service(careplan_id):
    try:
        careplan = CarePlan.objects.get(id=careplan_id)
    except CarePlan.DoesNotExist:
        return None

    if careplan.status == "completed":
        return {"status": "completed", "content": careplan.content}
    if careplan.status == "failed":
        return {"status": "failed"}
    return {"status": "pending"}