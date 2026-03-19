from rest_framework import serializers


class CreateOrderSerializer(serializers.Serializer):
    """
    Docstring for CreateOrderSerializer

    1. 定义字段和验证规则
    2. validate_开头的方法 → 针对单个字段的额外验证
    3. validate() 方法 → 针对多个字段之间关系的验证

    这个 Serializer 的作用是：
    1. 接收来自 views.py 的原始数据
    2. 验证数据是否合法（比如 NPI 是不是 10 位数字）
    3. 整理成一个干净的 validated_data 字典，交给 service 使用  

    注意：这个 Serializer 只负责验证和整理数据，不负责任何业务逻辑（比如检查 NPI 是否重复）
    业务逻辑应该放在 services.py 里。
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
    dob = serializers.DateField(required=False, default=None)
    confirm = serializers.BooleanField(required=False, default=False)

    def validate_npi(self, value):
        if not value.isdigit() or len(value) != 10:
            raise serializers.ValidationError("NPI must be exactly 10 digits.")
        return value

    def validate_mrn(self, value):
        if not value.isdigit() or len(value) != 6:
            raise serializers.ValidationError("MRN must be exactly 6 digits.")
        return value