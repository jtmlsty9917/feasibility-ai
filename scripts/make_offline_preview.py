"""离线生成一份"报告预览"（无需 API Key，用内置示例文本顶替 AI 章节）。

用途：在拿到真实 API Key 之前，先看到整份可研报告/Word 的成品结构，
也用于 README 截图与格式检查。示例文本会明确标注"预览示例"。
运行：.venv\\Scripts\\python scripts\\make_offline_preview.py
输出：data/outputs/可研报告_示例_离线预览.md 与 .docx
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 允许从任意目录运行本脚本：把项目根目录加入模块搜索路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feasibility_ai.engine import ProjectParams
from feasibility_ai.workflow.report import ReportPipeline
from feasibility_ai.reports import markdown_to_docx

OUT_DIR = Path("data/outputs")

MARKET_DRAFT = (
    "现制茶饮市场仍处增长期但增速放缓，一二线城市核心商圈竞争饱和，"
    "独立门店的竞争关键是选址、出品效率与复购。本项目选址学校周边，"
    "客群以学生为主，具备学期性客流特征，寒暑假为明显淡季。"
    "建议以差异化产品与会员复购对抗同质化竞争，并预留外卖平台渠道。"
    "（预览示例文本：真实使用时由大模型结合知识库撰写）"
)

RISK_DRAFT = (
    "主要风险：①客流不足——盈亏平衡需达到约 77% 设计产能，一旦客流下滑超两成即亏损，"
    "建议按淡季客流校核悲观情景；②租金上涨——敏感性分析显示固定成本对 NPV 影响显著，"
    "建议签订较长租约；③食安监管——需建立原料效期与清洁消毒台账（详见资料库引用）；"
    "④同质化竞争——持续迭代产品与会员运营。"
    "（预览示例文本：真实使用时由大模型结合测算结果与资料撰写）"
)


class DraftClient:
    """离线预览用假客户端：返回固定示例文本，不联网。"""

    def __init__(self) -> None:
        self.total_tokens = 0

    def chat_json(self, system: str, user: str) -> dict:
        self.total_tokens += 100  # 仅示意
        if "audit" in system:
            return {"audit": [
                {"field": "首年营业收入",
                 "question": "65 万元按日均约 1,780 元测算，旺季/淡季如何分布？是否已扣节假日闭店？",
                 "suggestion": "给出客流依据或改为区间假设并做悲观情景"},
                {"field": "年固定经营成本",
                 "question": "25.8 万元是否包含店主个人薪酬？若不包含，机会成本未计入会高估收益。",
                 "suggestion": "建议单列店主薪酬 8~12 万元/年，重新测算"},
                {"field": "收入年增速",
                 "question": "6% 的长期增速依据是什么？通常门店第三年后趋于平稳。",
                 "suggestion": "可改为前三年增长后持平的分段假设"},
            ]}
        if "市场分析" in system:
            return {"content": MARKET_DRAFT}
        if "风险分析与对策" in system:
            return {"content": RISK_DRAFT}
        return {"content": "（预览占位）"}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pipe = ReportPipeline(client=DraftClient())
    out = pipe.generate(ProjectParams())

    md_path = OUT_DIR / "可研报告_示例_离线预览.md"
    docx_path = OUT_DIR / "可研报告_示例_离线预览.docx"
    md_path.write_text(out["report_markdown"], encoding="utf-8")
    markdown_to_docx(out["report_markdown"], docx_path)

    print(f"已生成：{md_path}")
    print(f"已生成：{docx_path}")
    print(f"（预览共 {len(out['report_markdown'])} 字符；市场/风险章节为内置示例文本）")


if __name__ == "__main__":
    main()
