import re
from django.utils import timezone
from .models import Patient, Provider, Order, CarePlan
from .exceptions import BlockError, WarningException
from datetime import datetime

def process_clinic_order(clinic_b_data):
    warnings = []

    # ===== Step 1: 提取字段，转换格式 =====
    # 从 pt 里拿 patient 信息
    pt = clinic_b_data["pt"]
    mrn = pt["mrn"]
    patient_first_name = pt["fname"]
    patient_last_name = pt["lname"]
    dob = pt["dob"]  # 注意：格式是 "03/22/1985"，后面可能要转换

    # provider name 是 "Dr. Emily Johnson"，需要 split 拆成 first 和 last
    provider = clinic_b_data["provider"]
    npi = provider["npi_num"]
    full_name = provider["name"]  # "Dr. Emily Johnson"
    name_parts = full_name.replace("Dr. ", "").split()
    provider_first_name = name_parts[0]  # "Emily"
    provider_last_name = name_parts[1]   # "Johnson"

    # medication 在 rx 里面的 med_name
    medication = clinic_b_data["rx"]["med_name"]

    # diagnosis: 把 primary 和 secondary 合并成一个字符串
    dx = clinic_b_data["dx"]
    all_dx = [dx["primary"]] + dx["secondary"]  # ["G70.00", "E11.9", "I10"]
    diagnosis = ", ".join(all_dx)  # "G70.00, E11.9, I10"

    # medical history: list 变成 string
    medical_history = "\n".join(clinic_b_data["med_hx"])
    
    # ===== Step 2: 验证 =====
    # NPI 必须 10 位数字
    if not npi.isdigit() or len(npi) != 10:
        raise ValueError("NPI must be exactly 10 digits")

    # MRN 必须 6 位数字
    if not mrn.isdigit() or len(mrn) != 6:
        raise ValueError("MRN must be exactly 6 digits")

    # ICD-10 格式检查：字母开头，后面跟数字，可能有小数点
    for code in all_dx:
        if not re.match(r'^[A-Z]\d{2}(\.\d{1,2})?$', code):
            raise ValueError(f"Invalid ICD-10 code: {code}")
    
    # ===== Step 3: 重复检测 =====
    # ── Provider 检测 ──
    existing_provider = Provider.objects.filter(npi=npi).first()
    if existing_provider:
        if (existing_provider.first_name.strip().lower() != provider_first_name.strip().lower() or
            existing_provider.last_name.strip().lower() != provider_last_name.strip().lower()):
            # NPI 相同 + 名字不同 → ❌ 阻止
            raise BlockError(
                code="DUPLICATE_NPI",
                message="NPI is already registered to a different provider.",
                detail={
                    "npi": npi,
                    "existing": f"{existing_provider.first_name} {existing_provider.last_name}",
                    "incoming": f"{provider_first_name} {provider_last_name}",
                },
            )
        # NPI 相同 + 名字相同 → 复用现有
        provider = existing_provider
    else:
        provider = Provider.objects.create(
            npi=npi,
            first_name=provider_first_name,
            last_name=provider_last_name,
        )

    # ── Patient 检测 ──
    existing_by_mrn = Patient.objects.filter(mrn=mrn).first()
    existing_by_name_dob = Patient.objects.filter(
        first_name__iexact=patient_first_name,
        last_name__iexact=patient_last_name,
        dob=dob,
    ).exclude(mrn=mrn).first()

    if existing_by_mrn:
        # MRN 已存在，检查名字和 DOB 是否匹配
        name_match = (
            existing_by_mrn.first_name.strip().lower() == patient_first_name.strip().lower() and
            existing_by_mrn.last_name.strip().lower() == patient_last_name.strip().lower()
        )
        dob_match = (existing_by_mrn.dob == dob) if existing_by_mrn.dob and dob else True

        if not name_match or not dob_match:
            # MRN 相同 + 名字或 DOB 不同 → ⚠️ 警告
            warnings.append(WarningException(
                code="PATIENT_DATA_MISMATCH",
                message="MRN already exists but name or DOB differs. Using existing record.",
                detail={
                    "mrn": mrn,
                    "existing": f"{existing_by_mrn.first_name} {existing_by_mrn.last_name}",
                    "incoming": f"{patient_first_name} {patient_last_name}",
                },
            ).to_dict())
        # MRN 匹配 → 复用现有
        patient = existing_by_mrn

    elif existing_by_name_dob:
        # 名字 + DOB 相同 + MRN 不同 → ⚠️ 警告，但创建新记录
        warnings.append(WarningException(
            code="DUPLICATE_PATIENT_DIFFERENT_MRN",
            message="A patient with the same name and DOB exists with a different MRN.",
            detail={
                "existing_mrn": existing_by_name_dob.mrn,
                "incoming_mrn": mrn,
            },
        ).to_dict())
        patient = Patient.objects.create(
            mrn=mrn,
            first_name=patient_first_name,
            last_name=patient_last_name,
            dob=dob,
        )
    else:
        # 全新 patient
        patient = Patient.objects.create(
            mrn=mrn,
            first_name=patient_first_name,
            last_name=patient_last_name,
            dob=dob,
        )

    # ── Order 重复检测 ──
    today = timezone.now().date()

    # 同患者 + 同药物 + 同一天 → ❌ 阻止
    duplicate_today = Order.objects.filter(
        patient=patient,
        medication=medication,
        created_at__date=today,
    ).first()
    if duplicate_today:
        raise BlockError(
            code="DUPLICATE_ORDER_TODAY",
            message="An order for this patient and medication already exists today.",
            detail={
                "existing_order_id": duplicate_today.id,
                "patient": f"{patient.first_name} {patient.last_name}",
                "medication": medication,
                "date": str(today),
            },
        )

    # 同患者 + 同药物 + 不同天 → ⚠️ 警告（可能是续方）
    previous_order = Order.objects.filter(
        patient=patient,
        medication=medication,
    ).exclude(created_at__date=today).first()
    if previous_order:
        warnings.append(WarningException(
            code="PREVIOUS_ORDER_EXISTS",
            message="A previous order exists for this patient and medication.",
            detail={
                "existing_order_id": previous_order.id,
                "date": str(previous_order.created_at.date()),
            },
        ).to_dict())
    
    # ===== Step 4: 创建 Order 和 CarePlan，交给 Celery =====

    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication=medication,
        diagnosis=diagnosis,
        medical_history=medical_history,
    )

    care_plan = CarePlan.objects.create(order=order, status="pending")

    from orders.tasks import generate_care_plan
    generate_care_plan.delay(care_plan.id)

    return order, care_plan, warnings

def process_pharma_order(partner_c_data):
    warnings = []

    # ===== Step 1: 解析 XML，提取字段，转换格式 =====
    import xml.etree.ElementTree as ET

    # 把 XML 字符串解析成对象
    root = ET.fromstring(partner_c_data)

    # 从 PatientInformation 里拿 mrn, first_name, last_name, dob
    mrn = root.find(".//MedicalRecordNumber").text
    patient_first_name = root.find(".//PatientName/FirstName").text
    patient_last_name = root.find(".//PatientName/LastName").text
    dob_str = root.find(".//DateOfBirth").text  # "1972-11-30"
    dob = datetime.strptime(dob_str, "%Y-%m-%d").date()

    # provider 名字是 "Dr. Michael Chen"，要 split 拆开，拿 npi
    provider_full_name = root.find(".//PrescriberInformation/FullName").text
    name_parts = provider_full_name.replace("Dr. ", "").split()
    provider_first_name = name_parts[0]
    provider_last_name = name_parts[1]
    npi = root.find(".//PrescriberInformation/NPINumber").text

    # medication 在 MedicationOrder 里的 DrugName
    medication = root.find(".//MedicationOrder/DrugName").text

    # diagnosis: primary + 所有 secondary 的 ICDCode，合并成字符串
    primary_dx = root.find(".//PrimaryDiagnosis/ICDCode").text
    secondary_dx = [d.find("ICDCode").text for d in root.findall(".//SecondaryDiagnoses/Diagnosis")]
    all_dx = [primary_dx] + secondary_dx
    diagnosis = ", ".join(all_dx)

    # medical history: 每个 Medication 拼成 "Name Dosage Frequency"，再 join
    med_history_items = []
    for med in root.findall(".//MedicationHistory/Medication"):
        name = med.find("MedicationName").text
        dosage = med.find("Dosage").text
        freq = med.find("Frequency").text
        med_history_items.append(f"{name} {dosage} {freq}")
    medical_history = "\n".join(med_history_items)

    # ===== Step 2: 验证 =====

    if not npi.isdigit() or len(npi) != 10:
        raise ValueError("NPI must be exactly 10 digits")

    if not mrn.isdigit() or len(mrn) != 6:
        raise ValueError("MRN must be exactly 6 digits")

    for code in all_dx:
        if not re.match(r'^[A-Z]\d{2}(\.\d{1,2})?$', code):
            raise ValueError(f"Invalid ICD-10 code: {code}")

    # ===== Step 3: 重复检测 =====

    # ── Provider 检测 ──
    existing_provider = Provider.objects.filter(npi=npi).first()
    if existing_provider:
        if (existing_provider.first_name.strip().lower() != provider_first_name.strip().lower() or
            existing_provider.last_name.strip().lower() != provider_last_name.strip().lower()):
            raise BlockError(
                code="DUPLICATE_NPI",
                message="NPI is already registered to a different provider.",
                detail={
                    "npi": npi,
                    "existing": f"{existing_provider.first_name} {existing_provider.last_name}",
                    "incoming": f"{provider_first_name} {provider_last_name}",
                },
            )
        provider = existing_provider
    else:
        provider = Provider.objects.create(
            npi=npi,
            first_name=provider_first_name,
            last_name=provider_last_name,
        )

    # ── Patient 检测 ──
    existing_by_mrn = Patient.objects.filter(mrn=mrn).first()
    existing_by_name_dob = Patient.objects.filter(
        first_name__iexact=patient_first_name,
        last_name__iexact=patient_last_name,
        dob=dob,
    ).exclude(mrn=mrn).first()

    if existing_by_mrn:
        name_match = (
            existing_by_mrn.first_name.strip().lower() == patient_first_name.strip().lower() and
            existing_by_mrn.last_name.strip().lower() == patient_last_name.strip().lower()
        )
        dob_match = (existing_by_mrn.dob == dob) if existing_by_mrn.dob and dob else True

        if not name_match or not dob_match:
            warnings.append(WarningException(
                code="PATIENT_DATA_MISMATCH",
                message="MRN already exists but name or DOB differs. Using existing record.",
                detail={
                    "mrn": mrn,
                    "existing": f"{existing_by_mrn.first_name} {existing_by_mrn.last_name}",
                    "incoming": f"{patient_first_name} {patient_last_name}",
                },
            ).to_dict())
        patient = existing_by_mrn

    elif existing_by_name_dob:
        warnings.append(WarningException(
            code="DUPLICATE_PATIENT_DIFFERENT_MRN",
            message="A patient with the same name and DOB exists with a different MRN.",
            detail={
                "existing_mrn": existing_by_name_dob.mrn,
                "incoming_mrn": mrn,
            },
        ).to_dict())
        patient = Patient.objects.create(
            mrn=mrn,
            first_name=patient_first_name,
            last_name=patient_last_name,
            dob=dob,
        )
    else:
        patient = Patient.objects.create(
            mrn=mrn,
            first_name=patient_first_name,
            last_name=patient_last_name,
            dob=dob,
        )

    # ── Order 重复检测 ──
    today = timezone.now().date()

    duplicate_today = Order.objects.filter(
        patient=patient,
        medication=medication,
        created_at__date=today,
    ).first()
    if duplicate_today:
        raise BlockError(
            code="DUPLICATE_ORDER_TODAY",
            message="An order for this patient and medication already exists today.",
            detail={
                "existing_order_id": duplicate_today.id,
                "patient": f"{patient.first_name} {patient.last_name}",
                "medication": medication,
                "date": str(today),
            },
        )

    previous_order = Order.objects.filter(
        patient=patient,
        medication=medication,
    ).exclude(created_at__date=today).first()
    if previous_order:
        warnings.append(WarningException(
            code="PREVIOUS_ORDER_EXISTS",
            message="A previous order exists for this patient and medication.",
            detail={
                "existing_order_id": previous_order.id,
                "date": str(previous_order.created_at.date()),
            },
        ).to_dict())

    # ===== Step 4: 创建 Order 和 CarePlan，交给 Celery =====

    order = Order.objects.create(
        patient=patient,
        provider=provider,
        medication=medication,
        diagnosis=diagnosis,
        medical_history=medical_history,
    )

    care_plan = CarePlan.objects.create(order=order, status="pending")

    from orders.tasks import generate_care_plan
    generate_care_plan.delay(care_plan.id)

    return order, care_plan, warnings