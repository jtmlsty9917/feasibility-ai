"""可研报告编排（M2）：把"引擎测算 + 知识库 + 大模型"组装成完整报告。

安全设计（本项目灵魂，面试核心话术）：
- **财务章节 = 纯代码生成**：数字 100% 来自 engine.analyze 的 JSON，不经大模型；
- **大模型只写两章**（市场分析 / 风险分析），并在提示词中强制"只可用给定的已知事实，
  禁止编造财务数字"；
- **概述 / 实施要点 / 结论** 也由确定性模板生成（结论按 NPV/IRR 阈值规则判断）。
这样即使模型胡说，报告主体数字依然可信；配合后置校验即可交付。

LLM 依赖通过构造函数注入（便于单测用假客户端，不发真实请求）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ..engine import analyze, ProjectParams
from ..knowledge import KnowledgeBase

# ---------- 参数的中文解释（假设清单展示用）----------
PARAM_LABELS: dict[str, str] = {
    "name": "项目名称", "industry": "所属行业", "calc_years": "计算期（年）",
    "discount_rate": "基准折现率", "initial_investment": "建设投资（元）",
    "working_capital": "流动资金（元）", "first_year_revenue": "首年营业收入（元）",
    "revenue_growth": "收入年增速", "variable_cost_rate": "变动成本占收入比",
    "fixed_operating_cost": "年固定经营成本（元）", "depreciation_years": "折旧年限（年）",
    "salvage_rate": "残值率", "tax_rate": "所得税率",
    "annual_volume": "设计年销量（杯）", "unit_price": "平均单价（元/杯）",
}

# 注入到此接口的大模型对象只需有 chat_json/system 能力
class LLMProtocol:
    def chat_json(self, system: str, user: str) -> dict: ...  # pragma: no cover
    def chat_text(self, system: str, user: str) -> str: ...  # pragma: no cover
    total_tokens: int  # pragma: no cover


def build_assumption_markdown(p: ProjectParams) -> str:
    """把关键假设渲染成 Markdown 表格（界面展示 + 报告附录共用）。"""
    rows = []
    for attr, label in PARAM_LABELS.items():
        val = getattr(p, attr)
        if isinstance(val, float):
            if attr in ("discount_rate", "revenue_growth", "variable_cost_rate",
                        "salvage_rate", "tax_rate"):
                val = f"{val * 100:.1f}%"
            else:
                val = f"{val:,.0f}"
        rows.append(f"| {label} | {val} |")
    return "| 假设项 | 取值 |\n|---|---|\n" + "\n".join(rows)


def conclusion_decision(r: dict) -> str:
    """按 NPV/IRR 阈值给出结论（纯规则，无 LLM）。"""
    npv_ok = r["npv"] >= 0
    irr_ok = r["irr"] is not None and r["irr"] >= r["rate"]
    npv_wan = r["npv"] / 10000
    if npv_ok and irr_ok:
        head = f"**建议实施**：基准假设下 NPV ≈ {npv_wan:,.0f} 万元（≥0），"
        head += f"IRR ≈ {r['irr'] * 100:.1f}%（≥ 基准折现率 {r['rate'] * 100:.0f}%），项目在经济上可行。"
        head += " 但可行不等于无风险，请结合第四章风险与敏感性结论制定控制措施，并关注盈亏平衡产能占比"
        head += (f"（约 {r['bep']['bep_utilization'] * 100:.0f}%）。" if r["bep"]["bep_utilization"] else "。")
        return head
    if npv_ok and not irr_ok:
        return (f"**谨慎实施**：NPV ≈ {npv_wan:,.0f} 万元 ≥ 0，但现金流非常规或 IRR 无法唯一确定，"
                "建议以 NPV 为主判据并补充敏感性验证。"
                if r["irr"] is None else
                f"**谨慎实施**：NPV ≈ {npv_wan:,.0f} 万元但 IRR ≈ {r['irr'] * 100:.1f}% 低于基准折现率，"
                "建议重新审视收益假设或下调投资。")
    return (f"**不建议实施**（基准假设下）：NPV ≈ {npv_wan:,.0f} 万元 < 0，"
            "项目无法覆盖基准收益要求；若必须推进，需显著改善收入或成本结构后重新测算。")


def build_financial_section(r: dict) -> str:
    """财务测算章节：纯代码生成，数字全部来自引擎 JSON。"""
    bep = r["bep"]
    lines = [
        "> 本节全部数字由财务测算引擎计算（非 AI 生成）。",
        "",
        f"- 基准折现率：{r['rate'] * 100:.1f}%；计算期：{r['years']} 年",
        f"- **NPV（净现值）≈ {r['npv'] / 10000:,.0f} 万元**"
        + ("（≥0，基准假设下可行）" if r["npv"] >= 0 else "（<0，基准假设下不可行）"),
        f"- **IRR（内部收益率）≈ {r['irr'] * 100:.1f}%**" if r["irr"] is not None
        else "- IRR：现金流非常规，无法唯一求解，以 NPV 为主判据",
        f"- 静态投资回收期 ≈ {r['payback_static']:.2f} 年；"
        f"动态投资回收期 ≈ {r['payback_dynamic']:.2f} 年"
        if r["payback_static"] is not None else "- 回收期超出计算期，需关注",
    ]
    if bep["bep_volume"]:
        lines.append(f"- 盈亏平衡销量 ≈ {bep['bep_volume']:,.0f} 杯/年"
                     f"（约 {bep['bep_utilization'] * 100:.0f}% 设计产能；"
                     f"折合约 {bep['bep_daily']:,.0f} 杯/天）")
    lines += ["", "### 敏感性（参数 ±20% 对 NPV 的影响，从大到小）", ""]
    for row in reversed(r["sensitivity"]):  # 引擎已按幅度升序
        lines.append(f"- {row['label']}：NPV 变动范围 "
                     f"[{row['minus20'] / 10000:+,.0f} ~ {row['plus20'] / 10000:+,.0f}] 万元")
    lines += ["", "### 三情景对比", "",
              "| 情景 | NPV(万元) | IRR | 动态回收期 |", "|---|---|---|---|"]
    for s in r["scenarios"]:
        irr_txt = f"{s['irr'] * 100:.1f}%" if s["irr"] is not None else "不适用"
        pb_txt = f"{s['payback_dynamic']:.2f} 年" if s["payback_dynamic"] is not None else "超期"
        lines.append(f"| {s['情景']} | {s['npv'] / 10000:,.0f} | {irr_txt} | {pb_txt} |")
    return "\n".join(lines)


def _fetch_context(kb: Optional[KnowledgeBase], topic: str, k: int = 3) -> str:
    """从知识库检索与主题相关的片段，拼成带引用的"已知事实"文本。"""
    if kb is None or not kb.chunk_count:
        return "（未上传参考资料，本部分基于通用常识与模型自身知识，结论请人工复核。）"
    hits = kb.query(topic, k=k)
    parts = []
    for score, meta, text in hits:
        head = meta.get("heading") or ""
        src = meta.get("source", "未知来源")
        parts.append(f"[来源：{src}｜{head}]\n{text[:400]}")
    return "参考资料片段（带引用）：\n\n" + "\n\n".join(parts)


class ReportPipeline:
    """报告流水线。构造时注入大模型客户端（可为假对象）。"""

    def __init__(self, client: LLMProtocol, kb: Optional[KnowledgeBase] = None):
        self._client = client
        self._kb = kb
        self._before_tokens = getattr(client, "total_tokens", 0)

    # ---- 第一步：假设审核（人机协作）----
    def audit_assumptions(self, p: ProjectParams) -> list[dict]:
        sys_prompt = (
            "你是一位资深投资项目可行性研究专家。请审查用户给出的项目假设清单，"
            "找出最需要澄清、最容易过于乐观的 3~5 条，逐一提问。"
            '只输出 JSON：{"audit": [{"field": "参数名", "question": "具体疑问", '
            '"suggestion": "建议调整方向"}]}'
        )
        user = "项目假设清单：\n\n" + build_assumption_markdown(p)
        data = self._client.chat_json(sys_prompt, user)
        audit = data.get("audit") if isinstance(data, dict) else None
        return audit if isinstance(audit, list) else []

    # ---- 大模型执笔章节 ----
    def _write_narrative(self, system: str, user: str) -> str:
        """模型只输出正文；章节标题由 generate() 统一添加。

        强制模型输出 {"content": "<markdown 正文>"}；不同模型偶发使用其他键名，
        这里做兜底（取内容最长的字符串值），保证章节不因格式问题丢失。
        """
        data = self._client.chat_json(
            system,
            user
            + "\n只输出 Markdown 正文，不要输出章节标题（标题由系统统一添加）。\n"
              '输出格式：一个 JSON 对象 {"content": "正文纯字符串"}，'
              "content 的值是纯字符串，不要再嵌套对象或数组。",
        )
        if isinstance(data, dict):
            content = data.get("content")
            if not isinstance(content, str):
                # 兜底：模型偶发换键名时取最长的字符串值
                candidates = [v for v in data.values() if isinstance(v, str)]
                content = max(candidates, key=len) if candidates else None
        else:
            content = None
        if not content or not isinstance(content, str):
            return "（本节生成失败，请重试）"
        return content.strip()

    def market_section(self, p: ProjectParams, r: dict) -> str:
        known = (f"项目：{p.name}；行业：{p.industry}；首年收入假设 {p.first_year_revenue:,.0f} 元"
                 f"（增速 {p.revenue_growth * 100:.0f}%）；年固定经营成本 {p.fixed_operating_cost:,.0f} 元。")
        ctx = _fetch_context(self._kb, f"{p.industry} 市场规模 趋势 政策")
        system = (
            "你是行业分析专家。请撰写《可行性研究报告》的市场分析章节。\n"
            "铁律：只允许使用下面提供的'已知事实'，不得编造任何具体财务数字、"
            "统计数字或来源；不确定的内容写成定性描述并标注'（需进一步调研验证）'。"
        )
        user = f"已知事实：{known}\n\n{ctx}"
        return self._write_narrative(system, user)

    def risk_section(self, p: ProjectParams, r: dict) -> str:
        top = reversed(r["sensitivity"][-2:])  # 影响最大的两个参数
        sens_txt = "；".join(f"{row['label']}±20% 使 NPV 变化 "
                             f"{row['minus20'] / 10000:+.0f}~{row['plus20'] / 10000:+.0f} 万元"
                             for row in top)
        pes = [s for s in r["scenarios"] if s["情景"] == "悲观"][0]
        known = (f"悲观情景 NPV ≈ {pes['npv'] / 10000:,.0f} 万元；"
                 f"关键敏感参数：{sens_txt}。"
                 f"盈亏平衡产能占比约 {r['bep']['bep_utilization'] * 100:.0f}%。")
        ctx = _fetch_context(self._kb, f"{p.industry} 风险 监管 竞争")
        system = (
            "你是风险管理专家。请撰写《可行性研究报告》的风险分析与对策章节。\n"
            "铁律：只能引用下面'已知事实'中的测算数字；不得编造任何新数字；"
            "每类风险给出可操作的对策建议。"
        )
        user = f"已知事实（测算结果）：{known}\n\n{ctx}"
        return self._write_narrative(system, user)

    # ---- 汇总 ----
    def generate(self, p: ProjectParams,
                 audit: Optional[list[dict]] = None) -> dict:
        """生成整份报告，返回结构化结果。"""
        r = analyze(p)
        audit = audit if audit is not None else self.audit_assumptions(p)

        sections = {
            "一、项目概述": (
                f"### 1.1 项目简介\n{p.name}（{p.industry}）。本报告基于用户填写的假设参数，"
                f"由财务引擎完成测算、AI 辅助撰写叙述章节。\n\n"
                f"### 1.2 投资规模\n建设投资 {p.initial_investment:,.0f} 元"
                f"+ 流动资金 {p.working_capital:,.0f} 元"
                f"，计算期 {p.calc_years} 年，基准折现率 {p.discount_rate * 100:.0f}%。"
            ),
            "二、市场分析": self.market_section(p, r),
            "三、财务测算": build_financial_section(r),
            "四、风险分析与对策": self.risk_section(p, r),
            "五、结论与建议": conclusion_decision(r),
        }

        audit_md = "\n".join(
            f"{i + 1}. **{a.get('field', '')}**：{a.get('question', '')}"
            f"（建议：{a.get('suggestion', '')}）"
            for i, a in enumerate(audit)
        ) or "（AI 未提出额外疑问）"

        appendix = ("## 附录 A：假设清单\n\n" + build_assumption_markdown(p)
                    + "\n\n## 附录 B：假设审核意见\n\n" + audit_md)

        # 章节标题统一在此拼接（章节正文一律不自带标题）
        report = "\n\n".join(f"## {k}\n\n{sections[k]}" for k in sections)
        report += "\n\n" + appendix

        return {
            "report_markdown": report,
            "sections": sections,
            "audit": audit,
            "result": r,
            "tokens_used": max(getattr(self._client, "total_tokens", 0) - self._before_tokens, 0),
        }
