from rest_framework import serializers
from .models import Order, CarePlan


class CreateOrderSerializer(serializers.Serializer):
    """
    负责验证 POST /api/orders/ 的请求数据格式。
    目前只做字段声明，验证逻辑下一步再加。
    """
    mrn = serializers.CharField()
    patient_first_name = serializers.CharField()
    patient_last_name = serializers.CharField()
    npi = serializers.CharField()
    provider_first_name = serializers.CharField()
    provider_last_name = serializers.CharField()
    medication = serializers.CharField()
    diagnosis = serializers.CharField(required=False, default="")
    medical_history = serializers.CharField(required=False, default="")