"""RAG 链路自检：真实调用 Embedding，验证"上传资料 → 入库 → 检索"。

用法：.venv\\Scripts\\python scripts\\check_rag.py
说明：需要 .env 配好 EMBED_*（任一国内平台的 Embedding 接口）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feasibility_ai.llm import LLMClient, LLMNotConfiguredError
from feasibility_ai.knowledge import KnowledgeBase

SAMPLE_DOC = "data/samples/行业资料示例.md"


def main() -> int:
    try:
        llm = LLMClient()
    except LLMNotConfiguredError as e:
        print(f"✗ {e}")
        return 1

    # ① 验证 Embedding 接口
    try:
        vecs = llm.embed_texts(["向量化功能测试"])
    except Exception as e:
        print(f"✗ Embedding 调用失败：{e}")
        print("  检查：.env 的 EMBED_BASE_URL / EMBED_API_KEY / EMBED_MODEL 是否正确")
        return 1
    print(f"① Embedding 调用成功：向量维度 = {len(vecs[0])}")

    # ② 用样例资料建库
    kb = KnowledgeBase(embed_fn=llm.embed_texts)
    n = kb.add_document(SAMPLE_DOC)
    print(f"② 样例资料入库成功：{n} 个文本块（来源：{kb.sources}）")

    # ③ 检索
    hits = kb.query("食品安全监管的重点是什么？", k=3)
    if not hits:
        print("✗ 检索结果为空")
        return 1
    print("③ 检索链路正常，Top 命中：")
    for score, meta, text in hits:
        head = meta.get("heading") or ""
        print(f"   [{meta.get('source')} | {head}] 相似度 {score:.3f}: {text[:70]}...")
    print("\n✓ RAG 链路全部正常——标签③可直接使用（上传任意研报/政策即可问答）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
