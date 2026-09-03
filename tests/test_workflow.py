"""报告编排测试：用"假大模型"验证流程与数字安全，绝不发真实请求。

重点验证（面试口径的自动化保障）：
1. 财务章节是确定性生成的，与引擎 JSON 完全一致，与模型说什么无关；
2. 大模型只负责市场/风险叙述，其输出被正确嵌入；
3. 结论按规则给出，不依赖模型；
4. 假设审核 JSON 被正确解析。
"""
import pytest

from feasibility_ai.engine import ProjectParams, analyze
from feasibility_ai.workflow.report import (
    ReportPipeline,
    build_financial_section,
    conclusion_decision,
    build_assumption_markdown,
)


class FakeClient:
    """假大模型：按提示词返回预设 JSON；不联网。"""

    def __init__(self):
        self.total_tokens = 0
        self.chat_json_calls: list[tuple[str, str]] = []
        self.market_text = "市场整体处于成长期，竞争激烈，需关注差异化。（需进一步调研验证）"
        self.risk_text = "主要风险来自客流与租金波动，建议签订长租约并控制备货损耗。"

    def chat_json(self, system: str, user: str) -> dict:
        self.chat_json_calls.append((system, user))
        self.total_tokens += 100
        if "audit" in system:
            return {"audit": [
                {"field": "首年营业收入",
                 "question": "65 万/年按日均多少杯测算？旺季与淡季如何分布？",
                 "suggestion": "给出客流依据或改为区间假设"},
            ]}
        if "市场分析" in system:
            return {"content": self.market_text}
        if "风险分析与对策" in system:
            return {"content": self.risk_text}
        return {"content": "（未知章节）"}


def test_financial_section_matches_engine():
    p = ProjectParams()
    r = analyze(p)
    md = build_financial_section(r)
    # 确定性：含引擎 NPV 数值与"非 AI 生成"标注
    assert f"{r['npv'] / 10000:,.0f}" in md
    assert "财务测算引擎" in md
    assert "三情景对比" in md
    # 与模型无关：同样的引擎结果必然产生同样文本
    assert md == build_financial_section(analyze(p))


def test_conclusion_decision_rules():
    p = ProjectParams()  # 基准示例：NPV>0 且 IRR>折现率
    r = analyze(p)
    assert "建议实施" in conclusion_decision(r)

    bad = ProjectParams(
        first_year_revenue=200_000.0, fixed_operating_cost=300_000.0,
        initial_investment=500_000.0, working_capital=100_000.0,
    )
    rb = analyze(bad)
    txt = conclusion_decision(rb)
    assert ("不建议实施" in txt) or ("谨慎实施" in txt)
    if rb["npv"] >= 0:
        assert "谨慎实施" in txt
    else:
        assert "不建议实施" in txt


def test_assumption_markdown_table():
    md = build_assumption_markdown(ProjectParams())
    assert "首年营业收入" in md
    assert "|" in md


def test_pipeline_generates_full_report():
    fake = FakeClient()
    pipe = ReportPipeline(client=fake)  # 无知识库路径
    p = ProjectParams()
    out = pipe.generate(p)

    # 章节齐全（标题由 generate 统一添加）
    for key in ("一、项目概述", "二、市场分析", "三、财务测算",
                "四、风险分析与对策", "五、结论与建议"):
        assert f"## {key}" in out["report_markdown"]
    # 大模型被调用（市场+风险+审核）
    assert len(fake.chat_json_calls) == 3
    # 财务数字来自引擎而非模型
    r = analyze(p)
    assert f"{r['npv'] / 10000:,.0f}" in out["sections"]["三、财务测算"]
    assert fake.market_text in out["sections"]["二、市场分析"]
    # 结论与附录存在
    assert "附录 A" in out["report_markdown"]
    assert "附录 B" in out["report_markdown"]
    assert len(out["audit"]) == 1
    assert out["tokens_used"] == 300  # 3 次调用 × 100


def test_pipeline_with_failing_llm_still_safe():
    """模型抽风时：财务/结论章节不受影响（数字安全设计）。"""

    class BadClient(FakeClient):
        def chat_json(self, system: str, user: str) -> dict:
            self.total_tokens += 50
            return {"unexpected": "模型胡言乱语"}

    bad = BadClient()
    pipe = ReportPipeline(client=bad)
    out = pipe.generate(ProjectParams())
    r = analyze(ProjectParams())
    # 财务章节仍含正确数字；审核为空但不崩溃
    assert f"{r['npv'] / 10000:,.0f}" in out["sections"]["三、财务测算"]
    assert out["audit"] == []


def test_narrative_fallback_when_key_renamed():
    """模型把 content 换成其他键名时，兜底取最长字符串，章节不丢失。"""

    class RenamedKeyClient(FakeClient):
        def chat_json(self, system: str, user: str) -> dict:
            self.total_tokens += 50
            if "audit" in system:
                return {"audit": []}
            return {"text": "兜底正文：这是一段足够长的市场分析正文内容。"}

    c = RenamedKeyClient()
    pipe = ReportPipeline(client=c)
    out = pipe.generate(ProjectParams())
    assert "兜底正文" in out["sections"]["二、市场分析"]
