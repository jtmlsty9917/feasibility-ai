"""质检卡测试：正常报告应全过；故意损坏的报告应被正确揪出。"""
import pytest

from feasibility_ai.engine import analyze, ProjectParams
from feasibility_ai.workflow.report import build_financial_section, conclusion_decision
from feasibility_ai.qa import quality_card

HEADERS = ["## 一、项目概述", "## 二、市场分析", "## 三、财务测算",
           "## 四、风险分析与对策", "## 五、结论与建议",
           "## 附录 A", "## 附录 B"]


def make_out(r, market="市场整体处于成长期，需关注差异化。", risk="风险可控。"):
    financial = build_financial_section(r)
    sections = {
        "一、项目概述": "项目简介内容。",
        "二、市场分析": market,
        "三、财务测算": financial,
        "四、风险分析与对策": risk,
        "五、结论与建议": conclusion_decision(r),
    }
    appendix = "## 附录 A：假设清单\n...\n\n## 附录 B：假设审核意见\n..."
    md = "\n\n".join(f"## {k}\n\n{v}" for k, v in sections.items()) + "\n\n" + appendix
    return {"report_markdown": md, "sections": sections,
            "result": r, "tokens_used": 1000}


def test_clean_report_passes():
    r = analyze(ProjectParams())
    out = make_out(r)
    card = quality_card(out, kb_had_content=False)
    assert card["n_fail"] == 0
    status = {c["name"]: c["status"] for c in card["checks"]}
    assert status["章节完整"] == "pass"
    assert status["关键数字齐全"] == "pass"
    assert status["AI 章节疑似新数字"] == "pass"
    assert status["引用完整性"] == "na"


def test_missing_chapter_is_fail():
    r = analyze(ProjectParams())
    out = make_out(r)
    financial = build_financial_section(r)
    # 删除整个"财务测算"章节（标题+正文）
    out["report_markdown"] = out["report_markdown"].replace(
        f"## 三、财务测算\n\n{financial}", "")
    out["sections"].pop("三、财务测算", None)
    card = quality_card(out, kb_had_content=False)
    by_name = {c["name"]: c for c in card["checks"]}
    assert by_name["章节完整"]["status"] == "fail"
    assert by_name["关键数字齐全"]["status"] == "fail"  # 数字锚点随财务章节一起消失


def test_fabricated_number_is_warned():
    r = analyze(ProjectParams())
    risk = "未来三年项目将累计亏损约 88 万元，需警惕。（88 不在白名单）"
    out = make_out(r, market="行业规模约 5 亿元。", risk=risk)
    card = quality_card(out, kb_had_content=False)
    by_name = {c["name"]: c for c in card["checks"]}
    # 88 万元：不在引擎已知数字内 → 提示
    assert by_name["AI 章节疑似新数字"]["status"] == "warn"
    # 5 亿元带单位"亿元"，不在 SUSPECT_UNITS（万元/元/杯）判定里，不误报
    assert "5 亿" not in by_name["AI 章节疑似新数字"]["detail"]


def test_kb_without_citation_warns():
    r = analyze(ProjectParams())
    out = make_out(r)
    card = quality_card(out, kb_had_content=True)
    by_name = {c["name"]: c for c in card["checks"]}
    assert by_name["引用完整性"]["status"] == "warn"


def test_year_number_not_flagged():
    r = analyze(ProjectParams())
    risk = "参照 2026 年市场情况。"
    out = make_out(r, risk=risk)
    card = quality_card(out, kb_had_content=False)
    by_name = {c["name"]: c for c in card["checks"]}
    assert by_name["AI 章节疑似新数字"]["status"] == "pass"
