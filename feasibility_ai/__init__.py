"""FeasAI 核心包：项目可行性研究 AI 助手。

模块划分（详见 docs/architecture.md）：
- engine/    财务测算引擎（纯 Python，无 LLM 依赖）—— 全项目的信任基石
- knowledge/ 文档解析 / 向量检索（RAG，M2 启用）
- llm/       大模型客户端（国内 API，M2 启用）
- workflow/  可研报告编排（M2 启用）
- reports/   报告模板与导出（M3 启用）
"""
