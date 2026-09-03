"""大模型客户端（M2）：统一封装国内各家 OpenAI 兼容 API（DeepSeek/通义/智谱等）。

设计要点：
- 配置全部来自项目根目录 .env（模板见 .env.example），换厂商只需改 3 个变量；
- 懒加载：不调用就不建立连接，未配置 Key 时抛出可读错误，界面据此优雅降级；
- 记录累计 token，供界面展示"这次消耗"（省钱提示，符合非功能需求）。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv(encoding="utf-8")  # 读取项目根目录的 .env（显式 UTF-8）
except Exception:  # 测试环境无 dotenv 时静默
    pass


class LLMNotConfiguredError(RuntimeError):
    """未配置 API Key / 服务地址时抛出。"""


@dataclass
class LLMSettings:
    """大模型与 Embedding 服务的连接配置（OpenAI 兼容协议）。"""

    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    embed_base_url: str = ""
    embed_api_key: str = ""
    embed_model: str = ""

    @classmethod
    def from_env(cls) -> "LLMSettings":
        s = cls(
            llm_base_url=os.getenv("LLM_BASE_URL", "").strip(),
            llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
            llm_model=os.getenv("LLM_MODEL", "").strip(),
            embed_base_url=os.getenv("EMBED_BASE_URL", "").strip(),
            embed_api_key=os.getenv("EMBED_API_KEY", "").strip(),
            embed_model=os.getenv("EMBED_MODEL", "").strip(),
        )
        if not (s.llm_base_url and s.llm_api_key and s.llm_model):
            raise LLMNotConfiguredError(
                "未检测到 LLM 配置。请把项目根目录的 .env.example 复制为 .env，"
                "填入 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL（如 DeepSeek），然后重启应用。"
            )
        return s

    @classmethod
    def is_configured(cls) -> bool:
        try:
            cls.from_env()
            return True
        except LLMNotConfiguredError:
            return False


class LLMClient:
    """统一入口：chat_text / chat_json / embed_texts。"""

    def __init__(self, settings: LLMSettings | None = None):
        self.settings = settings or LLMSettings.from_env()
        self.total_tokens = 0  # 累计 token 消耗（界面展示用）
        self._chat = None
        self._embed = None

    # ---------- 内部懒加载 ----------
    def _require_chat(self):
        if self._chat is None:
            import openai

            self._chat = openai.OpenAI(
                base_url=self.settings.llm_base_url,
                api_key=self.settings.llm_api_key,
            )
        return self._chat

    def _require_embed(self):
        if self._embed is None:
            if not (self.settings.embed_base_url and self.settings.embed_api_key):
                raise LLMNotConfiguredError(
                    "未配置 Embedding 服务（EMBED_BASE_URL / EMBED_API_KEY）。"
                    "可在 .env 填入硅基流动 SiliconFlow（BGE 系列有免费档）或智谱 embedding 服务。"
                )
            import openai

            self._embed = openai.OpenAI(
                base_url=self.settings.embed_base_url,
                api_key=self.settings.embed_api_key,
            )
        return self._embed

    # ---------- 对外能力 ----------
    def chat_text(self, system: str, user: str, temperature: float = 0.3) -> str:
        """普通文本补全。"""
        resp = self._require_chat().chat.completions.create(
            model=self.settings.llm_model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        self._count(resp)
        return (resp.choices[0].message.content or "").strip()

    def chat_json(self, system: str, user: str, temperature: float = 0.2) -> dict:
        """要求模型输出 JSON 对象（国内模型普遍支持 json_object 模式）。

        容错链：优先 response_format=json_object；个别厂商不支持时降级为
        普通补全并剥掉 ```json 代码块包裹；仍失败则抛解析错误。
        """
        content = None
        try:
            resp = self._require_chat().chat.completions.create(
                model=self.settings.llm_model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system
                     + "\n只输出一个合法 JSON 对象，不要输出任何其他文字。"},
                    {"role": "user", "content": user},
                ],
            )
            content = resp.choices[0].message.content
            self._count(resp)
        except Exception:
            # 可能是不支持 response_format：降级为普通补全
            resp = self._require_chat().chat.completions.create(
                model=self.settings.llm_model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user + "\n请用 JSON 对象格式回答。"},
                ],
            )
            content = resp.choices[0].message.content
            self._count(resp)

        raw = (content or "{}").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"模型输出不是合法 JSON：{raw[:200]}……（{e}）") from e

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化（按输入顺序返回向量列表）。"""
        resp = self._require_embed().embeddings.create(
            model=self.settings.embed_model,
            input=texts,
        )
        ordered = sorted(resp.data, key=lambda d: d.index)
        return [list(d.embedding) for d in ordered]

    def _count(self, resp) -> None:
        try:
            self.total_tokens += int(resp.usage.total_tokens)
        except Exception:
            pass


__all__ = ["LLMClient", "LLMSettings", "LLMNotConfiguredError"]
