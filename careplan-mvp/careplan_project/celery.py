import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "careplan_project.settings")

app = Celery("careplan_project")

# 从 Django settings 里读配置，所有 Celery 配置以 CELERY_ 开头
app.config_from_object("django.conf:settings", namespace="CELERY")

# 自动发现每个 app 下的 tasks.py
app.autodiscover_tasks()