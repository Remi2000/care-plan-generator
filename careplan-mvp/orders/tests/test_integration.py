import pytest
from unittest.mock import patch
from orders.models import Patient, Provider, Order, CarePlan


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def base_payload():
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
    }


# ─────────────────────────────────────────────
# POST /api/orders/
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestCreateOrderAPI:

    @patch("orders.tasks.generate_care_plan.delay")
    def test_success_returns_201(self, mock_delay, api_client, base_payload):
        res = api_client.post("/api/orders/", base_payload, format="json")
        assert res.status_code == 201
        assert "order_id" in res.data
        assert "careplan_id" in res.data
        assert res.data["warnings"] == []

    @patch("orders.tasks.generate_care_plan.delay")
    def test_celery_task_is_called(self, mock_delay, api_client, base_payload):
        api_client.post("/api/orders/", base_payload, format="json")
        assert mock_delay.called

    def test_invalid_npi_returns_400(self, api_client, base_payload):
        base_payload["npi"] = "abc"
        res = api_client.post("/api/orders/", base_payload, format="json")
        assert res.status_code == 400
        assert res.data["type"] == "validation"
        assert res.data["code"] == "VALIDATION_ERROR"

    def test_missing_medication_returns_400(self, api_client, base_payload):
        del base_payload["medication"]
        res = api_client.post("/api/orders/", base_payload, format="json")
        assert res.status_code == 400
        assert res.data["type"] == "validation"

    @patch("orders.tasks.generate_care_plan.delay")
    def test_duplicate_npi_different_name_returns_409(self, mock_delay, api_client, base_payload):
        api_client.post("/api/orders/", base_payload, format="json")
        base_payload["provider_last_name"] = "Smyth"
        base_payload["mrn"] = "MRN002"
        res = api_client.post("/api/orders/", base_payload, format="json")
        assert res.status_code == 409
        assert res.data["code"] == "DUPLICATE_NPI"

    @patch("orders.tasks.generate_care_plan.delay")
    def test_duplicate_order_today_returns_409(self, mock_delay, api_client, base_payload):
        api_client.post("/api/orders/", base_payload, format="json")
        res = api_client.post("/api/orders/", base_payload, format="json")
        assert res.status_code == 409
        assert res.data["code"] == "DUPLICATE_ORDER_TODAY"

    @patch("orders.tasks.generate_care_plan.delay")
    def test_success_response_has_warnings_field(self, mock_delay, api_client, base_payload):
        res = api_client.post("/api/orders/", base_payload, format="json")
        assert "warnings" in res.data


# ─────────────────────────────────────────────
# GET /api/orders/<id>/
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestGetOrderAPI:

    @patch("orders.tasks.generate_care_plan.delay")
    def test_get_existing_order_returns_200(self, mock_delay, api_client, base_payload):
        post_res = api_client.post("/api/orders/", base_payload, format="json")
        order_id = post_res.data["order_id"]
        res = api_client.get(f"/api/orders/{order_id}/")
        assert res.status_code == 200
        assert res.data["medication"] == "Humira"

    def test_get_nonexistent_order_returns_404(self, api_client):
        res = api_client.get("/api/orders/99999/")
        assert res.status_code == 404


# ─────────────────────────────────────────────
# GET /api/careplan/<id>/status/
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestCarePlanStatusAPI:

    @patch("orders.tasks.generate_care_plan.delay")
    def test_status_is_pending_after_create(self, mock_delay, api_client, base_payload):
        post_res = api_client.post("/api/orders/", base_payload, format="json")
        careplan_id = post_res.data["careplan_id"]
        res = api_client.get(f"/api/careplan/{careplan_id}/status/")
        assert res.status_code == 200
        assert res.data["status"] == "pending"

    def test_nonexistent_careplan_returns_404(self, api_client):
        res = api_client.get("/api/careplan/99999/status/")
        assert res.status_code == 404