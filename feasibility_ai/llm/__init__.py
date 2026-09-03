"""大模型模块（M2 启用）：统一封装国内各家 OpenAI 兼容 API。

- client.LLMClient：文本补全 / JSON 结构化输出 / Embedding 向量化；
- 配置来自 .env（模板见 .env.example）：LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
  与 EMBED_* 分别配置，可一键切换厂商（DeepSeek / 通义 / 智谱 / 硅基流动等）；
- 未配置 Key 时抛出 LLMNotConfiguredError，界面优雅降级（AI 功能置灰并给引导）。
"""
from .client import LLMClient, LLMSettings, LLMNotConfiguredError

__all__ = ["LLMClient", "LLMSettings", "LLMNotConfiguredError"]
