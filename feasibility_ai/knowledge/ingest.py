"""文档解析与切块。

- 纯文本（txt/md）直接读取；PDF/Word/Excel 交给微软开源库 markitdown（MIT）；
- 切块策略（借鉴 RAGFlow 思路的简化版）：
  按 Markdown 标题(#)分段 → 段超长先按空行分段落 → 段落仍超长则按
  字符滑动窗口切（窗口 max_chars，步长 max_chars - overlap，保留上下文）。
- 每个文本块的元数据记录 来源文件 + 所属标题，检索命中后可直接做引用。
"""
from __future__ import annotations

import re
from pathlib import Path

PLAIN_EXTS = {".txt", ".md", ".markdown"}
DEFAULT_MAX_CHARS = 1100   # 每块目标长度（约等于一次 embedding 的合理粒度）
DEFAULT_OVERLAP = 120      # 滑动窗口重叠，避免切断语义


class DocumentParseError(RuntimeError):
    """文档读取/解析失败（含未安装 markitdown）。"""


def parse_document(path: str | Path) -> str:
    """把任意受支持文档读成纯文本（Markdown 风格）。"""
    p = Path(path)
    if not p.exists():
        raise DocumentParseError(f"文件不存在：{p}")
    if p.suffix.lower() in PLAIN_EXTS:
        return p.read_text(encoding="utf-8", errors="ignore")
    try:
        from markitdown import MarkItDown
    except ImportError as e:  # pragma: no cover
        raise DocumentParseError(
            "未安装 markitdown：pip install 'markitdown[pdf]'"
        ) from e
    try:
        result = MarkItDown().convert(str(p))
        return result.text_content or ""
    except Exception as e:
        raise DocumentParseError(f"解析 {p.suffix} 失败：{e}") from e


def chunk_markdown(text: str, source: str = "文档",
                   max_chars: int = DEFAULT_MAX_CHARS,
                   overlap: int = DEFAULT_OVERLAP) -> list[dict]:
    """把整篇文本切成带元数据的块。

    返回：[{"chunk_id", "source", "heading", "text"}, ...]
    """
    out: list[dict] = []
    source_name = Path(source).name

    def push(body: str, heading: str) -> None:
        t = body.strip()
        if t:
            out.append({
                "chunk_id": len(out),
                "source": source_name,
                "heading": heading,
                "text": t,
            })

    def chunk_long(para: str, heading: str) -> None:
        """超长段落：滑动窗口切块。"""
        step = max(max_chars - overlap, 1)
        for i in range(0, len(para), step):
            push(para[i:i + max_chars], heading)

    # 1) 按标题分组：记录当前标题，收集其下所有行
    sections: list[tuple[str, list[str]]] = []
    heading = ""
    buf: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            body = "\n".join(buf).strip()
            if body:
                sections.append((heading, [body]))
            buf = []
            heading = stripped.lstrip("#").strip()
        else:
            buf.append(line)
    body = "\n".join(buf).strip()
    if body:
        sections.append((heading, [body]))

    # 2) 组内再切：段超长按段落切，段落超长滑动切
    for h, bodies in sections:
        for b in bodies:
            if len(b) <= max_chars:
                push(b, h)
                continue
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", b) if p.strip()]
            if not paragraphs:  # 无空行分段
                chunk_long(b, h)
                continue
            for para in paragraphs:
                if len(para) <= max_chars:
                    push(para, h)
                else:
                    chunk_long(para, h)
    return out
