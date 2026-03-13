import os
import sys
import django
import redis
import json
import time

# ====================================================
# Django 环境初始化
# 因为 worker.py 在 Django app 外面，
# 需要手动告诉 Python："去哪里找 Django 的配置"
# ====================================================
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "careplan_project.settings")
django.setup()

# Django 初始化之后，才能 import models
import anthropic
from django.conf import settings
from orders.models import CarePlan

def process_careplan(careplan_id):
    """
    拿到 careplan_id，生成 care plan，存回数据库
    """
    print(f"[Worker] 开始处理 careplan_id={careplan_id}")

    # Step 1: 从数据库拿到 CarePlan 和关联的 Order
    try:
        care_plan = CarePlan.objects.select_related("order__patient", "order__provider").get(id=careplan_id)
    except CarePlan.DoesNotExist:
        print(f"[Worker] ❌ careplan_id={careplan_id} 不存在，跳过")
        return

    # Step 2: 把 status 改成 processing
    care_plan.status = "processing"
    care_plan.save()
    print(f"[Worker] status → processing")

    # Step 3: 拼 prompt，调用 Claude
    order = care_plan.order
    prompt = f"""
You are a clinical pharmacist. Generate a care plan for the following patient order.

Patient: {order.patient.first_name} {order.patient.last_name}
MRN: {order.patient.mrn}
Provider: Dr. {order.provider.first_name} {order.provider.last_name}
Medication: {order.medication}
Diagnosis: {order.diagnosis}
Medical History: {order.medical_history}

Please provide a structured care plan including:
1. Medication overview
2. Dosing instructions
3. Monitoring parameters
4. Patient education points
5. Follow-up recommendations
"""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text
        print(f"[Worker] ✅ Claude 返回成功")

        # Step 4: 存回数据库
        care_plan.content = content
        care_plan.status = "completed"
        care_plan.save()
        print(f"[Worker] ✅ careplan_id={careplan_id} 已完成，status → completed")

    except Exception as e:
        care_plan.status = "failed"
        care_plan.save()
        print(f"[Worker] ❌ 出错了: {e}")


def run():
    """
    主循环：不断从 Redis 拉任务
    """
    r = redis.from_url(settings.REDIS_URL)
    print("[Worker] 启动，等待任务...")

    while True:
        # blpop：阻塞式拉取，有任务才返回，没任务就一直等
        # timeout=5 表示最多等 5 秒，没任务就返回 None（避免死等）
        result = r.blpop("careplan_queue", timeout=5)

        if result is None:
            # 5秒内没有任务，继续等
            print("[Worker] 没有任务，继续等待...")
            continue

        # result 是 (queue_name, data) 的元组
        _, data = result
        task = json.loads(data)
        careplan_id = task["careplan_id"]

        process_careplan(careplan_id)


if __name__ == "__main__":
    run()