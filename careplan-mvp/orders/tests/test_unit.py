import pytest
from django.utils import timezone
from unittest.mock import patch
from orders.models import Patient, Provider, Order, CarePlan
from orders.exceptions import BlockError, WarningException
from orders.services import create_order_service
from orders.serializers import CreateOrderSerializer


# ─────────────────────────────────────────────
# Fixtures：每个测试都可以用的基础数据
# ─────────────────────────────────────────────

@pytest.fixture
def base_data():
    """最基本的合法请求数据"""
    return {
        "mrn": "MRN001",
        "patient_first_name": "John",
        "patient_last_name": "Doe",
        "dob": "1990-01-01",
        "npi": "1234567890",
        "provider_first_name": "Alice",
        "provider_last_name": "Smith",
        "medication": "Humira",
        "diagnosis": "RA",
        "medical_history": "None",
        "confirm": False,
    }


@pytest.fixture
def existing_provider():
    return Provider.objects.create(
        npi="1234567890",
        first_name="Alice",
        last_name="Smith",
    )


@pytest.fixture
def existing_patient():
    return Patient.objects.create(
        mrn="MRN001",
        first_name="John",
        last_name="Doe",
        dob="1990-01-01",
    )


# ─────────────────────────────────────────────
# Serializer 验证测试
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestSerializerValidation:

    def test_valid_data_passes(self, base_data):
        s = CreateOrderSerializer(data=base_data)
        assert s.is_valid(), s.errors

    def test_npi_must_be_10_digits(self, base_data):
        base_data["npi"] = "abc"
        s = CreateOrderSerializer(data=base_data)
        assert not s.is_valid()
        assert "npi" in s.errors

    def test_npi_cannot_be_9_digits(self, base_data):
        base_data["npi"] = "123456789"  # 9位
        s = CreateOrderSerializer(data=base_data)
        assert not s.is_valid()
        assert "npi" in s.errors

    def test_npi_cannot_be_letters(self, base_data):
        base_data["npi"] = "123456789a"
        s = CreateOrderSerializer(data=base_data)
        assert not s.is_valid()
        assert "npi" in s.errors

    def test_mrn_cannot_be_empty(self, base_data):
        base_data["mrn"] = "   "
        s = CreateOrderSerializer(data=base_data)
        assert not s.is_valid()
        assert "mrn" in s.errors

    def test_medication_is_required(self, base_data):
        del base_data["medication"]
        s = CreateOrderSerializer(data=base_data)
        assert not s.is_valid()
        assert "medication" in s.errors

    def test_diagnosis_is_optional(self, base_data):
        del base_data["diagnosis"]
        s = CreateOrderSerializer(data=base_data)
        assert s.is_valid(), s.errors


# ─────────────────────────────────────────────
# Provider 重复检测测试
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestProviderDuplicateDetection:

    @patch("orders.tasks.generate_care_plan.delay")
    def test_same_npi_same_name_reuses_provider(self, mock_delay, base_data, existing_provider):
        """NPI + 名字都一样 → 复用，不报错"""
        order, care_plan, warnings = create_order_service(base_data)
        assert Provider.objects.count() == 1  # 没有新建

    @patch("orders.tasks.generate_care_plan.delay")
    def test_same_npi_different_name_raises_block(self, mock_delay, base_data, existing_provider):
        """NPI 相同但名字不同 → BlockError"""
        base_data["provider_last_name"] = "Smyth"
        with pytest.raises(BlockError) as exc_info:
            create_order_service(base_data)
        assert exc_info.value.code == "DUPLICATE_NPI"

    @patch("orders.tasks.generate_care_plan.delay")
    def test_new_npi_creates_provider(self, mock_delay, base_data):
        """全新 NPI → 创建新 Provider"""
        order, care_plan, warnings = create_order_service(base_data)
        assert Provider.objects.count() == 1


# ─────────────────────────────────────────────
# Patient 重复检测测试
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestPatientDuplicateDetection:

    @patch("orders.tasks.generate_care_plan.delay")
    def test_same_mrn_same_name_reuses_patient(self, mock_delay, base_data, existing_patient):
        """MRN + 名字都一样 → 复用，无 warning"""
        order, care_plan, warnings = create_order_service(base_data)
        assert Patient.objects.count() == 1
        assert not any(w["code"] == "PATIENT_DATA_MISMATCH" for w in warnings)

    @patch("orders.tasks.generate_care_plan.delay")
    def test_same_mrn_different_name_warns(self, mock_delay, base_data, existing_patient):
        """MRN 相同但名字不同 → warning"""
        base_data["patient_first_name"] = "Johnny"
        order, care_plan, warnings = create_order_service(base_data)
        assert any(w["code"] == "PATIENT_DATA_MISMATCH" for w in warnings)

    @patch("orders.tasks.generate_care_plan.delay")
    def test_same_name_dob_different_mrn_warns(self, mock_delay, base_data, existing_patient):
        """名字+DOB 相同但 MRN 不同 → warning，创建新 Patient"""
        base_data["mrn"] = "MRN999"
        order, care_plan, warnings = create_order_service(base_data)
        assert any(w["code"] == "DUPLICATE_PATIENT_DIFFERENT_MRN" for w in warnings)
        assert Patient.objects.count() == 2

    @patch("orders.tasks.generate_care_plan.delay")
    def test_new_patient_creates_record(self, mock_delay, base_data):
        """全新患者 → 创建，无 warning"""
        order, care_plan, warnings = create_order_service(base_data)
        assert Patient.objects.count() == 1
        assert warnings == []


# ─────────────────────────────────────────────
# Order 重复检测测试
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestOrderDuplicateDetection:

    @patch("orders.tasks.generate_care_plan.delay")
    def test_duplicate_order_today_raises_block(self, mock_delay, base_data, existing_patient):
        """同一天同一患者同一药 → BlockError"""
        provider = Provider.objects.create(
            npi="1234567890", first_name="Alice", last_name="Smith"
        )
        Order.objects.create(
            patient=existing_patient,
            provider=provider,
            medication="Humira",
        )
        with pytest.raises(BlockError) as exc_info:
            create_order_service(base_data)
        assert exc_info.value.code == "DUPLICATE_ORDER_TODAY"

    @patch("orders.tasks.generate_care_plan.delay")
    def test_previous_order_without_confirm_raises_block(self, mock_delay, base_data, existing_patient):
        """有历史订单，没有 confirm → BlockError"""
        provider = Provider.objects.create(
            npi="1234567890", first_name="Alice", last_name="Smith"
        )
        yesterday = timezone.now() - timezone.timedelta(days=1)
        order = Order.objects.create(
            patient=existing_patient,
            provider=provider,
            medication="Humira",
        )
        Order.objects.filter(id=order.id).update(created_at=yesterday)

        with pytest.raises(BlockError) as exc_info:
            create_order_service(base_data)
        assert exc_info.value.code == "PREVIOUS_ORDER_EXISTS"

    @patch("orders.tasks.generate_care_plan.delay")
    def test_previous_order_with_confirm_warns(self, mock_delay, base_data, existing_patient):
        """有历史订单，confirm=True → warning，允许继续"""
        provider = Provider.objects.create(
            npi="1234567890", first_name="Alice", last_name="Smith"
        )
        yesterday = timezone.now() - timezone.timedelta(days=1)
        order = Order.objects.create(
            patient=existing_patient,
            provider=provider,
            medication="Humira",
        )
        Order.objects.filter(id=order.id).update(created_at=yesterday)

        base_data["confirm"] = True
        order, care_plan, warnings = create_order_service(base_data)
        assert any(w["code"] == "PREVIOUS_ORDER_ACKNOWLEDGED" for w in warnings)