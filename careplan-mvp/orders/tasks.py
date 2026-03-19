from celery import shared_task
from .models import CarePlan
from .llm_services import get_llm_service


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
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
        return

    # Step 2: 改成 processing
    care_plan.status = "processing"
    care_plan.save()
    print(f"[Celery] status → processing")

    # Step 3: 调用 LLM 生成 Care Plan
    # 重构前：这里有 30 行代码（拼 prompt + if/else mock/claude + 调 API）
    # 重构后：一行搞定。切换 LLM 只需要改环境变量 LLM_PROVIDER
    try:
        llm = get_llm_service()
        content = llm.generate(care_plan.order)
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