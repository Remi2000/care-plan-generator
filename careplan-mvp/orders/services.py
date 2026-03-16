from .models import Patient, Provider, Order, CarePlan


def create_order_service(data):
    """
    业务逻辑：创建 Patient / Provider / Order / CarePlan，把任务丢给 Celery。
    返回 (order, care_plan)
    """
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

    care_plan = CarePlan.objects.create(
        order=order,
        status="pending",
    )
    print("===== STEP 5: CarePlan 已存数据库, status=pending =====")

    from orders.tasks import generate_care_plan
    generate_care_plan.delay(care_plan.id)
    print(f"===== STEP 6: careplan_id={care_plan.id} 已交给 Celery =====")

    return order, care_plan


def get_order_service(pk):
    """
    查询单个 Order 及其 CarePlan 状态。
    返回 dict，找不到返回 None。
    """
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
    """
    按姓名 / MRN 搜索订单，返回 list of dict。
    """
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
    """
    获取 care plan 的纯文本内容，供下载用。
    返回 (order, content) 或 (None, error_str)。
    """
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
    """
    查询 CarePlan 状态。
    返回 dict 或 None。
    """
    try:
        careplan = CarePlan.objects.get(id=careplan_id)
    except CarePlan.DoesNotExist:
        return None

    if careplan.status == "completed":
        return {"status": "completed", "content": careplan.content}
    if careplan.status == "failed":
        return {"status": "failed"}
    return {"status": "pending"}