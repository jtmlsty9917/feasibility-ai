"""知识库（M2）：文档 → 切块 → 向量化 → 检索（RAG 的资料底座）。

设计（借鉴 RAGFlow 思路的自研简化版，学思路不抄代码）：
- ingest：txt/md 直接读，PDF/Word/Excel 走微软开源 markitdown（MIT）；
- chunk：按标题切块（见 ingest.chunk_markdown），每块带来源与标题元数据；
- embed：Embedding 模型由外部注入（默认 llm.LLMClient.embed_texts，
  支持硅基流动 BGE 免费档 / 智谱等国内服务）；
- retrieve：自研 numpy 余弦 top-k（store.VectorStore），命中块可直接做引用。

KnowledgeBase 是会话级内存对象：M2 阶段"上传资料 → 建库 → 问答/报告引用"够用；
P2 需要跨会话持久化时，把 store 换成 chroma/FAISS + 落盘即可（接口不变）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List

from .ingest import parse_document, chunk_markdown, DocumentParseError
from .store import VectorStore

# Embedding 函数类型：输入文本列表，输出等长向量列表
EmbedFn = Callable[[List[str]], List[List[float]]]

# 直接支持的扩展名（其余交给 markitdown 尝试）
SUPPORTED_EXTS = {".txt", ".md", ".markdown", ".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".html"}


class KnowledgeBase:
    """轻量知识库：add_document 入库，query 检索。"""

    def __init__(self, embed_fn: EmbedFn):
        if not callable(embed_fn):
            raise TypeError("embed_fn 必须是可调用对象（接收文本列表返回向量列表）")
        self._embed_fn = embed_fn
        self._store = VectorStore()
        self._documents: dict[str, int] = {}  # source -> 块数

    # ---------- 写入 ----------
    def add_document(self, path: str | Path) -> int:
        """解析并入库一个文档，返回生成的块数。"""
        p = Path(path)
        if not p.exists():
            raise DocumentParseError(f"文件不存在：{p}")
        text = parse_document(p)
        chunks = chunk_markdown(text, source=str(p))
        if not chunks:
            raise DocumentParseError(f"未能从 {p.name} 提取有效内容")
        texts = [c["text"] for c in chunks]
        metas = [{k: v for k, v in c.items() if k != "text"} for c in chunks]
        vectors = self._embed_fn(texts)
        self._store.add(texts, metas, vectors)
        self._documents[p.name] = self._documents.get(p.name, 0) + len(chunks)
        return len(chunks)

    def add_folder(self, folder: str | Path) -> int:
        """批量入库文件夹内的受支持文档，返回总块数。"""
        total = 0
        for p in sorted(Path(folder).iterdir()):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                total += self.add_document(p)
        return total

    # ---------- 检索 ----------
    def query(self, question: str, k: int = 5) -> list[tuple[float, dict, str]]:
        """返回 [(score, meta, text), ...]，调用方负责展示与引用。"""
        if not self._store:
            return []
        vec = self._embed_fn([question])[0]
        return self._store.search(vec, k=k)

    # ---------- 状态 ----------
    def clear(self) -> None:
        self._store = VectorStore()
        self._documents = {}

    @property
    def chunk_count(self) -> int:
        return len(self._store)

    @property
    def sources(self) -> list[str]:
        return sorted(self._documents)

    def __repr__(self) -> str:  # pragma: no cover
        return (f"KnowledgeBase(块数={self.chunk_count}, "
                f"文档={len(self._documents)})")


__all__ = ["KnowledgeBase", "parse_document", "chunk_markdown",
           "DocumentParseError", "VectorStore", "SUPPORTED_EXTS"]
