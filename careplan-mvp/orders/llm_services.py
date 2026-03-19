import os
from abc import ABC, abstractmethod
import anthropic
from django.conf import settings


# ============================================================
# BaseLLMService: 抽象基类
# 对应 adapters.py 里的 BaseIntakeAdapter
# ============================================================

class BaseLLMService(ABC):

    def build_prompt(self, order):
        """
        共享逻辑 — 所有 LLM 用同一个 prompt
        对应 adapter 里的 validate()：不管数据从哪来，验证规则都一样
        这里：不管用哪个 LLM，prompt 都一样
        """
        return f"""
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

    @abstractmethod
    def call_api(self, prompt):
        """
        每个 LLM 不同的部分 — 子类必须重写
        对应 adapter 里的 parse() 和 transform()
        参数: prompt 字符串
        返回: care plan 文本字符串
        """
        pass

    def generate(self, order):
        """
        统一入口 — 对应 adapter 里的 process()
        业务代码只调这一个方法，不需要知道内部细节

        process() 是: parse → transform → validate → return dict
        generate() 是: build_prompt → call_api → return string
        """
        prompt = self.build_prompt(order)
        return self.call_api(prompt)


# ============================================================
# ClaudeService: 调用 Anthropic Claude API
# 对应 adapters.py 里的 ClinicAdapter
# ============================================================

class ClaudeService(BaseLLMService):

    def call_api(self, prompt):
        """只重写 call_api — 其他都继承基类"""
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text


# ============================================================
# OpenAIService: 调用 OpenAI API
# 对应 adapters.py 里的 PharmaAdapter
# ============================================================

class OpenAIService(BaseLLMService):

    def call_api(self, prompt):
        """只重写 call_api — 调用方式不同，但输入输出格式一样"""
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content


# ============================================================
# MockLLMService: 开发测试用
# 对应 adapters.py 里的 MetroAdapter（第三个实现）
# ============================================================

class MockLLMService(BaseLLMService):

    def call_api(self, prompt):
        """不调任何 API，立刻返回假数据"""
        return (
            "[MOCK] 这是测试用的 Care Plan\n\n"
            "1. Medication overview: Mock data\n"
            "2. Dosing instructions: Mock data\n"
            "3. Monitoring parameters: Mock data\n"
            "4. Patient education points: Mock data\n"
            "5. Follow-up recommendations: Mock data"
        )


# ============================================================
# 工厂函数: 根据环境变量返回对应的 service
# 对应 adapters.py 里的 get_adapter()
# ============================================================

def get_llm_service() -> BaseLLMService:
    """
    新增 LLM 只需要:
    1. 写一个 XxxService 类
    2. 在这个 dict 里加一行
    tasks.py 完全不用改 — Open/Closed Principle
    """
    services = {
        "claude": ClaudeService,
        "openai": OpenAIService,
        "mock": MockLLMService,
    }

    provider = os.environ.get("LLM_PROVIDER", "mock")
    service_class = services.get(provider)

    if not service_class:
        raise ValueError(f"Unknown LLM provider: {provider}")

    return service_class()