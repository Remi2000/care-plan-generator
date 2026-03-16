# orders/exceptions.py


class BaseAppException(Exception):
    """
    所有业务异常的基类。
    定义统一格式：type, code, message, detail, http_status
    """
    type = "error"          # 子类覆盖
    http_status = 400       # 子类覆盖

    def __init__(self, code, message, detail=None):
        self.code = code
        self.message = message
        self.detail = detail or {}
        super().__init__(message)

    def to_dict(self):
        return {
            "type":    self.type,
            "code":    self.code,
            "message": self.message,
            "detail":  self.detail,
        }


class ValidationError(BaseAppException):
    """
    输入格式不对：NPI 不是10位、MRN 不是6位
    → 400 Bad Request
    """
    type = "validation"
    http_status = 400


class BlockError(BaseAppException):
    """
    业务规则阻止：同一 NPI 对应不同 Provider
    → 409 Conflict
    """
    type = "block"
    http_status = 409


class WarningException(BaseAppException):
    """
    业务警告：可能重复的患者，用户确认后可继续
    → 200 但带 warnings 字段（不走 exception_handler）
    """
    type = "warning"
    http_status = 200