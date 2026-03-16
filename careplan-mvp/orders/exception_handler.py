# orders/exception_handler.py

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from .exceptions import BaseAppException


def app_exception_handler(exc, context):
    """
    统一出口：
    1. 认识 BaseAppException → 转成统一 JSON
    2. 认识 DRF 自带的错误 → 也转成统一格式
    3. 其他未知错误 → 交还给 DRF 默认处理
    """

    # 情况1：我们自己的业务异常
    if isinstance(exc, BaseAppException):
        return Response(exc.to_dict(), status=exc.http_status)

    # 情况2：DRF 自带的 ValidationError（serializer 抛出的）
    # 先让 DRF 处理，拿到它的 response，再改成我们的格式
    response = drf_exception_handler(exc, context)

    if response is not None:
        # DRF 处理了，把格式统一成我们的结构
        return Response({
            "type":    "validation",
            "code":    "VALIDATION_ERROR",
            "message": "Invalid input",
            "detail":  response.data,   # DRF 的原始错误信息放进 detail
        }, status=response.status_code)

    # 情况3：DRF 也不认识 → 返回 None，Django 会给 500
    return None