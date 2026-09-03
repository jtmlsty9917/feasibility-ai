"""自研轻量向量检索（numpy 余弦相似度）。

为什么不用 chroma/FAISS（面试问答素材）：
- demo 规模（几百个文本块）用 numpy 矩阵乘法绰绰有余，响应 < 10ms；
- 零额外依赖、零部署，作者"本机只跑 Python"即可运行，代码一看就懂；
- 换向量库是"改一个类"的事：本文件对外只暴露 add/search，接口不变。
"""
from __future__ import annotations

import numpy as np


class VectorStore:
    """内存向量库：存文本块 + 元数据 + 归一化向量，支持余弦 top-k 检索。"""

    def __init__(self) -> None:
        self._matrix: np.ndarray | None = None  # 形状 (N, dim)，行已归一化
        self._items: list[dict] = []            # 与行一一对应：{"meta":..., "text":...}

    def __len__(self) -> int:
        return len(self._items)

    def add(self, texts: list[str], metas: list[dict],
            vectors: list[list[float]]) -> None:
        """批量加入：texts[i] 与 metas[i]、vectors[i] 对应。"""
        if not texts:
            return
        arr = np.asarray(vectors, dtype="float32")
        if arr.ndim != 2:
            raise ValueError("vectors 必须是二维数组 (N, dim)")
        if len(arr) != len(texts) or len(arr) != len(metas):
            raise ValueError("texts / metas / vectors 数量不一致")
        arr = arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12)  # 归一化
        self._matrix = arr if self._matrix is None else np.vstack([self._matrix, arr])
        self._items.extend(
            {"meta": metas[i], "text": texts[i]} for i in range(len(texts))
        )

    def search(self, vector: list[float], k: int = 5) -> list[tuple[float, dict, str]]:
        """余弦相似度 top-k。返回 [(score, meta, text), ...]，score 越高越相关。"""
        if not self._items:
            return []
        q = np.asarray(vector, dtype="float32")
        q = q / (np.linalg.norm(q) + 1e-12)
        sims = self._matrix @ q  # 矩阵乘法一次算全部余弦
        top = np.argsort(sims)[::-1][:k]
        return [
            (float(sims[i]), dict(self._items[i]["meta"]), self._items[i]["text"])
            for i in top
        ]
