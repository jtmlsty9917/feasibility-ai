"""客观质量卡（模型测评-第一版）：生成报告后的自动质检。

设计哲学（面试口径）：
- 只测"机器能客观判定"的项；语义质量（写得好不好、建议专不专业）交给人工，
  不假装机器能评——避免"测了个寂寞"。
- "疑似编造数字"设计成 ⚠️ 提示级而非 ❌ 否决级：需要区分"财务编造"与
  "合理的建议性数字（如 3 年租约）"，这个判断交给人不交给正则，避免误杀。

检查项：
① 结构完整性（5 章节 + 2 附录标题齐全）        → 过/不过
② 关键数字齐全（NPV/IRR/回收期/盈亏平衡/三情景） → 过/不过
③ AI 章节疑似新数字（不在引擎"已知事实"白名单内）→ 过/提示
④ 引用完整性（有知识库时应有 [来源）             → 过/提示/不适用
⑤ 成本与耗时（记录型）                          → 信息
"""
from __future__ import annotations

import re
from typing import Optional

HEADINGS = [
    "## 一、项目概述", "## 二、市场分析", "## 三、财务测算",
    "## 四、风险分析与对策", "## 五、结论与建议",
    "## 附录 A", "## 附录 B",
]

# 只对"万元 / 元 / 杯"这类财务单位做疑似检查；百分比与"年/月/倍"等允许表达
SUSPECT_UNITS = ("万元", "万", "元", "杯")
_NUM_RE = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*(万元|万|元|杯)")


def _normalize_num(s: str) -> str:
    """去千分位、去正号，统一为可比对字符串。"""
    return s.replace(",", "").replace("+", "")


def _fmt_wan(v: float) -> str:
    return f"{v / 10000:,.0f}"


def _collect_allowed(result: dict) -> set[str]:
    """把引擎输出的关键数字都收进白名单（与提示词给 AI 的'已知事实'一致）。"""
    allowed: set[str] = set()
    r = result

    def add(v) -> None:
        for s in (v, v.replace(",", "")):
            allowed.add(s)

    add(f"{_fmt_wan(r['npv'])}")
    if r.get("irr") is not None:
        add(f"{r['irr'] * 100:.1f}")
    if r.get("payback_static") is not None:
        add(f"{r['payback_static']:.2f}")
    if r.get("payback_dynamic") is not None:
        add(f"{r['payback_dynamic']:.2f}")
    bep = r.get("bep", {})
    if bep.get("bep_volume"):
        add(f"{bep['bep_volume']:,.0f}")
        add(f"{bep['bep_utilization'] * 100:.0f}")
    if bep.get("bep_daily"):
        add(f"{bep['bep_daily']:,.0f}")
    for s in r.get("scenarios", []):
        if s.get("npv") is not None:
            add(_fmt_wan(s["npv"]))
        if s.get("irr") is not None:
            add(f"{s['irr'] * 100:.1f}")
        if s.get("payback_dynamic") is not None:
            add(f"{s['payback_dynamic']:.2f}")
    for row in r.get("sensitivity", []):
        add(_fmt_wan(row["minus20"]))
        add(_fmt_wan(row["plus20"]))
    return {_normalize_num(v) for v in allowed}


def _is_year(s: str) -> bool:
    try:
        return 1900 <= int(s) <= 2100
    except ValueError:
        return False


def _check_structure(report_md: str) -> tuple[bool, list[str]]:
    missing = [h for h in HEADINGS if h not in report_md]
    return (not missing, missing)


def _check_anchors(report_md: str, r: dict) -> tuple[bool, list[str]]:
    """关键数字与要素必须出现在报告中（格式与报告生成代码完全一致）。"""
    anchors = [f"NPV（净现值）≈ {_fmt_wan(r['npv'])} 万元"]
    if r.get("irr") is not None:
        anchors.append(f"IRR（内部收益率）≈ {r['irr'] * 100:.1f}%")
    if r.get("payback_dynamic") is not None:
        anchors.append(f"动态投资回收期 ≈ {r['payback_dynamic']:.2f} 年")
    anchors += ["盈亏平衡销量", "三情景对比"]
    missing = [a for a in anchors if a not in report_md]
    return (not missing, missing)


def _check_suspect_numbers(sections: dict, allowed: set[str]) -> list[str]:
    """在 AI 执笔章节（市场/风险）里找不在白名单内的财务单位数字。"""
    suspects = []
    for key in ("二、市场分析", "四、风险分析与对策"):
        text = sections.get(key, "")
        for m in _NUM_RE.finditer(text):
            raw_num, unit = m.group(1), m.group(2)
            norm = _normalize_num(raw_num)
            if norm in allowed or _is_year(norm):
                continue
            # 摘取上下文
            start = max(0, m.start() - 18)
            ctx = text[start:m.end() + 6].replace("\n", " ")
            suspects.append(f"[{key}] “{ctx}…”")
    return suspects


def quality_card(out: dict, kb_had_content: bool) -> dict:
    """生成质检卡。out 为 ReportPipeline.generate() 的返回值。"""
    md: str = out.get("report_markdown", "")
    sections: dict = out.get("sections", {})
    r: dict = out.get("result", {})

    checks = []

    ok_struct, missing_h = _check_structure(md)
    checks.append({
        "name": "章节完整",
        "status": "pass" if ok_struct else "fail",
        "detail": "5 章节 + 2 附录齐全" if ok_struct
        else "缺少：" + "、".join(missing_h),
    })

    ok_anchor, missing_a = _check_anchors(md, r)
    checks.append({
        "name": "关键数字齐全",
        "status": "pass" if ok_anchor else "fail",
        "detail": "NPV/IRR/回收期/盈亏平衡/三情景均出现" if ok_anchor
        else "缺少：" + "；".join(missing_a),
    })

    allowed = _collect_allowed(r)
    suspects = _check_suspect_numbers(sections, allowed)
    checks.append({
        "name": "AI 章节疑似新数字",
        "status": "pass" if not suspects else "warn",
        "detail": "未发现白名单外的财务数字" if not suspects
        else f"发现 {len(suspects)} 处疑似，请人工核对：" + "；".join(suspects[:3]),
    })

    if kb_had_content:
        cites = sum(1 for k in ("二、市场分析", "四、风险分析与对策")
                    if "[来源" in sections.get(k, ""))
        checks.append({
            "name": "引用完整性",
            "status": "pass" if cites >= 1 else "warn",
            "detail": f"AI 章节含 {cites} 处 [来源] 引用" if cites >= 1
            else "知识库有内容但 AI 章节未出现 [来源]，请留意",
        })
    else:
        checks.append({"name": "引用完整性", "status": "na", "detail": "未使用知识库，不适用"})

    checks.append({
        "name": "成本与耗时",
        "status": "info",
        "detail": f"耗时记录见生成时间；tokens={out.get('tokens_used', 0):,}",
    })

    return {
        "checks": checks,
        "n_pass": sum(1 for c in checks if c["status"] == "pass"),
        "n_warn": sum(1 for c in checks if c["status"] == "warn"),
        "n_fail": sum(1 for c in checks if c["status"] == "fail"),
    }
