import os
import anthropic
from celery import shared_task
from django.conf import settings
from .models import CarePlan


def mock_generate_care_plan(prompt):
    """开发测试用的假 LLM，立刻返回，不调用任何 API"""
    return "[MOCK] 这是测试用的 Care Plan，不是真实的 LLM 输出。\n\n1. Medication overview: Mock data\n2. Dosing instructions: Mock data\n3. Monitoring parameters: Mock data\n4. Patient education points: Mock data\n5. Follow-up recommendations: Mock data"


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 第一次重试等 60 秒
)
def generate_care_plan(self, careplan_id):
    """
    Celery 异步任务：生成 Care Plan
    - bind=True：让 self 指向这个任务本身，用于重试
    - max_retries=3：最多重试 3 次
    - default_retry_delay=60：基础等待时间（指数退避会在此基础上翻倍）
    """
    print(f"[Celery] 开始处理 careplan_id={careplan_id}")

    # Step 1: 查数据库
    try:
        care_plan = CarePlan.objects.select_related(
            "order__patient", "order__provider"
        ).get(id=careplan_id)
    except CarePlan.DoesNotExist:
        print(f"[Celery] ❌ careplan_id={careplan_id} 不存在，放弃")
        return  # 不重试，直接放弃

    # Step 2: 改成 processing
    care_plan.status = "processing"
    care_plan.save()
    print(f"[Celery] status → processing")

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
        use_mock = os.environ.get('USE_MOCK_LLM') == 'True'

        if use_mock:
            print(f"[Celery] 使用 MOCK LLM（开发模式）")
            content = mock_generate_care_plan(prompt)
        else:
            # 生产环境：调用真实 LLM
            # 切换方式：把 docker-compose.yml 里的 USE_MOCK_LLM 改成 "False"
            client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            message = client.messages.create(
                model="claude-opus-4-5",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            content = message.content[0].text
        print(f"[Celery] ✅ Care Plan 返回成功")

        # Step 4: 存回数据库
        care_plan.content = content
        care_plan.status = "completed"
        care_plan.save()
        print(f"[Celery] ✅ careplan_id={careplan_id} 完成")

    except Exception as exc:
        print(f"[Celery] ❌ 出错: {exc}，准备重试（第 {self.request.retries + 1} 次）")
        care_plan.status = "failed"
        care_plan.save()

        # 指数退避：第1次等60s，第2次等120s，第3次等240s
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))