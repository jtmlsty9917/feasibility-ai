"""LLM 客户端测试：只测配置与错误路径，绝不发起真实网络调用。"""
import os

import pytest

from feasibility_ai.llm.client import (
    LLMClient,
    LLMSettings,
    LLMNotConfiguredError,
)


def _wipe_env(monkeypatch):
    for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
              "EMBED_BASE_URL", "EMBED_API_KEY", "EMBED_MODEL"):
        monkeypatch.delenv(k, raising=False)


def test_from_env_raises_when_missing(monkeypatch):
    _wipe_env(monkeypatch)
    with pytest.raises(LLMNotConfiguredError, match="LLM_API_KEY"):
        LLMSettings.from_env()
    assert LLMSettings.is_configured() is False


def test_client_constructed_from_env(monkeypatch):
    _wipe_env(monkeypatch)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    client = LLMClient()
    assert client.total_tokens == 0  # 懒加载：未调用前无任何网络动作
    assert LLMSettings.is_configured() is True


def test_embed_without_config_raises(monkeypatch):
    _wipe_env(monkeypatch)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    # 未配置 EMBED_* → embed_texts 应给出可读错误，而不是网络报错
    client = LLMClient()
    with pytest.raises(LLMNotConfiguredError, match="EMBED"):
        client.embed_texts(["测试"])


def test_settings_object_passthrough():
    s = LLMSettings(llm_base_url="http://x", llm_api_key="k",
                    llm_model="m", embed_base_url="http://e",
                    embed_api_key="ek", embed_model="em")
    c = LLMClient(settings=s)
    assert c.settings is s
