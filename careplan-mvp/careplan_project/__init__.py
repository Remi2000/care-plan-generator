# 这两行让 Django 启动时自动加载 Celery app
# 确保 @shared_task 能正常工作
from .celery import app as celery_app

__all__ = ("celery_app",)