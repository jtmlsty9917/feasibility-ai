"""知识库模块测试：切块、入库、检索（用假 Embedding，不调网络）。

假 Embedding 设计：固定词表 ["奶茶","咖啡","门店","卫生","光伏","电站","补贴","政策"]，
文本含某词则对应维度 +1。这样"语义"就是词袋重合度，可预测检索结果。
"""
import pytest

from feasibility_ai.knowledge import KnowledgeBase, chunk_markdown
from feasibility_ai.knowledge.ingest import DocumentParseError

VOCAB = ["奶茶", "咖啡", "门店", "卫生", "光伏", "电站", "补贴", "政策"]


def fake_embed(texts: list[str]) -> list[list[float]]:
    out = []
    for t in texts:
        v = [0.0] * len(VOCAB)
        for i, w in enumerate(VOCAB):
            if w in t:
                v[i] += 1.0
        out.append(v)
    return out


# ---------- 切块 ----------

def test_chunk_markdown_by_heading():
    text = "# 门店概况\n\n地段好，人流量大。\n\n## 财务测算\n\n收入 65 万。"
    chunks = chunk_markdown(text, source="示例.md")
    assert len(chunks) >= 2
    assert all(c["source"] == "示例.md" for c in chunks)
    headings = [c["heading"] for c in chunks]
    assert "门店概况" in headings
    assert "财务测算" in headings
    # 每个块的 chunk_id 连续
    assert [c["chunk_id"] for c in chunks] == list(range(len(chunks)))


def test_chunk_long_text_is_bounded():
    para = "这是一段很长的内容。" * 200  # 2000 字，超过 max_chars
    text = "# 长文\n\n" + para
    chunks = chunk_markdown(text, max_chars=1100, overlap=120)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c["text"]) <= 1100 + 120  # 不超上限（含重叠容差）


# ---------- 入库与检索 ----------

def test_add_and_query(tmp_path):
    doc_a = tmp_path / "奶茶店报告.md"
    doc_a.write_text(
        "# 奶茶门店卫生\n\n门店卫生是奶茶行业监管重点。\n\n## 补贴\n\n部分地区有创业补贴政策。",
        encoding="utf-8",
    )
    doc_b = tmp_path / "光伏电站.md"
    doc_b.write_text(
        "# 光伏电站补贴政策\n\n电站补贴按度电发放，政策逐年退坡。",
        encoding="utf-8",
    )

    kb = KnowledgeBase(embed_fn=fake_embed)
    kb.add_document(doc_a)
    kb.add_document(doc_b)
    # doc_a 有 2 个标题（2 块），doc_b 有 1 个标题（1 块），共 3 块
    assert kb.chunk_count == 3
    assert set(kb.sources) == {"奶茶店报告.md", "光伏电站.md"}

    # 查询奶茶卫生 → 应命中 doc_a 的内容
    hits = kb.query("奶茶 门店 卫生", k=2)
    assert hits, "检索不应为空"
    top_source = hits[0][1]["source"]
    assert top_source == "奶茶店报告.md"

    # 查询光伏补贴 → 应命中 doc_b（且得分高于奶茶店文档）
    hits_b = kb.query("光伏 电站 补贴", k=2)
    assert hits_b[0][1]["source"] == "光伏电站.md"


def test_query_empty_kb_returns_empty():
    kb = KnowledgeBase(embed_fn=fake_embed)
    assert kb.query("任何问题") == []


def test_clear(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("奶茶政策内容", encoding="utf-8")
    kb = KnowledgeBase(embed_fn=fake_embed)
    kb.add_document(p)
    assert kb.chunk_count > 0
    kb.clear()
    assert kb.chunk_count == 0


def test_missing_file_raises():
    kb = KnowledgeBase(embed_fn=fake_embed)
    with pytest.raises(DocumentParseError):
        kb.add_document("不存在.pdf")
