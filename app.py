"""FeasAI · 主界面(M2 版）：三标签页。

① 财务测算 —— 纯引擎计算，不依赖任何 AI 配置，离线可用；
② AI 可研报告 —— 假设审核 → 市场/风险 AI 执笔 → 财务/结论代码生成；
③ 资料问答(RAG)—— 上传研报/政策 → 建索引 → 带引用问答。

未配置 .env 的 API Key 时，②③ 会显示引导并自动降级，不影响 ①。
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dataclasses import asdict

from feasibility_ai.engine import analyze, ProjectParams
from feasibility_ai.llm import LLMClient
from feasibility_ai.knowledge import KnowledgeBase, DocumentParseError
from feasibility_ai.workflow.report import ReportPipeline
from feasibility_ai.reports import markdown_to_docx
from feasibility_ai.archive import list_projects, save_project, load_project
from feasibility_ai.qa import quality_card

UPLOAD_DIR = Path("data/uploaded")
EXPORT_DIR = Path("data/exported")
PROJECTS_DIR = Path("data/projects")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------- 配置探测（不改 .env 也能知道缺什么）----------
def ai_status() -> dict:
    llm_ok = bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_BASE_URL"))
    embed_ok = bool(os.getenv("EMBED_API_KEY") and os.getenv("EMBED_BASE_URL"))
    return {"llm": llm_ok, "embed": embed_ok}


def cfg_banner(need: str) -> None:
    """need: 'llm' 或 'embed' 或 'both'，按缺什么给对应提示。"""
    s = ai_status()
    if need in ("llm", "both") and not s["llm"]:
        st.warning(
            "🔑 未配置 DeepSeek（LLM_API_KEY）：标签② AI 报告与③ 资料问答暂不可用，"
            "① 财务测算不受影响。\n\n"
            "操作：把项目根目录 `.env.example` 复制为 `.env`，填入 LLM_API_KEY（DeepSeek）后重启应用。"
        )
        return
    if need in ("embed", "both") and not s["embed"]:
        st.info(
            "ℹ️ 标签③「上传资料问答」是**可选功能**，需要额外的向量化（Embedding）服务。\n\n"
            "当前 DeepSeek 已就绪——**标签② AI 可研报告完全可用**，不需要任何额外配置。\n\n"
            "以后想启用③时（可选）：在 `.env` 中取消注释 `EMBED_BASE_URL / EMBED_API_KEY / "
            "EMBED_MODEL` 三行并填入任一国内平台的 Embedding 接口（推荐硅基流动 BGE 免费档；"
            "智谱、通义、百度等均可），重启应用即可。"
        )


# ---------- 格式化 ----------
def fmt_wan(v) -> str:
    return "—" if v is None else f"{v / 10000:,.1f} 万元"


def fmt_pct(v, d: int = 1) -> str:
    return "—" if v is None else f"{v * 100:.{d}f}%"


def fmt_years(v) -> str:
    return "超出计算期" if v is None else f"{v:.2f} 年"


# ---------- 项目档案（记忆系统：本地存档/载入）----------
# 引擎属性 → (界面控件 key, 百分比换算因子)；factor 为 100 表示控件存的是百分比
PARAM_WIDGET_KEYS = {
    "name": ("in_name", None),
    "calc_years": ("in_years", None),
    "discount_rate": ("in_rate", 100.0),
    "initial_investment": ("in_invest", None),
    "working_capital": ("in_wc", None),
    "first_year_revenue": ("in_revenue", None),
    "revenue_growth": ("in_growth", 100.0),
    "variable_cost_rate": ("in_vcr", 100.0),
    "fixed_operating_cost": ("in_fixed", None),
    "depreciation_years": ("in_dep_years", None),
    "salvage_rate": ("in_salvage", 100.0),
    "tax_rate": ("in_tax", 100.0),
    "annual_volume": ("in_volume", None),
    "unit_price": ("in_price", None),
}


def apply_widget_values(params: dict) -> None:
    """把档案里的引擎参数(小数域)写回界面控件(百分比域)。"""
    for attr, (key, factor) in PARAM_WIDGET_KEYS.items():
        if attr not in params:
            continue
        v = params[attr]
        if factor:
            v = v * factor
        if isinstance(v, float) and attr in ("calc_years", "depreciation_years"):
            v = int(v)
        st.session_state[key] = v


def archive_controls() -> None:
    """顶部栏：载入历史项目 / 保存当前项目（记忆系统入口）。"""
    projects = list_projects(PROJECTS_DIR)
    labels = {f"{it['name']}（{it['saved_at'][:16].replace('T', ' ')}）": it["file"]
              for it in projects}

    c1, c2 = st.columns([3, 1])
    with c1:
        sel = st.selectbox("📂 项目档案：载入历史项目", ["（不载入）", *labels],
                           key="archive_select")
        applied = st.session_state.get("archive_applied", "（不载入）")
        if sel != "（不载入）" and sel != applied:
            try:
                data = load_project(PROJECTS_DIR, labels[sel])
                apply_widget_values(data["params"])
                st.session_state["archive_applied"] = sel
                st.success(f"已载入项目：{data['name']}")
            except Exception as e:
                st.error(f"载入失败：{e}")
        elif sel == "（不载入）":
            st.session_state["archive_applied"] = "（不载入）"
        if applied != "（不载入）":
            st.caption(f"当前档案：{applied}（改动后请重新保存）")
    with c2:
        if st.button("💾 保存当前项目为档案"):
            p = build_params()
            save_project(PROJECTS_DIR, p.name, asdict(p))
            st.success(f"已保存档案：{p.name}")


# ---------- 参数与测算 ----------
def build_params() -> ProjectParams:
    return ProjectParams(
        name=st.session_state.in_name,
        industry="餐饮零售",
        calc_years=int(st.session_state.in_years),
        discount_rate=st.session_state.in_rate / 100.0,
        initial_investment=float(st.session_state.in_invest),
        working_capital=float(st.session_state.in_wc),
        first_year_revenue=float(st.session_state.in_revenue),
        revenue_growth=st.session_state.in_growth / 100.0,
        variable_cost_rate=st.session_state.in_vcr / 100.0,
        fixed_operating_cost=float(st.session_state.in_fixed),
        depreciation_years=int(st.session_state.in_dep_years),
        salvage_rate=st.session_state.in_salvage / 100.0,
        tax_rate=st.session_state.in_tax / 100.0,
        annual_volume=float(st.session_state.in_volume),
        unit_price=float(st.session_state.in_price),
    )


def params_editor() -> None:
    with st.expander("📝 项目参数（默认：学校旁咖啡店示例）", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("项目名称", value="学校旁咖啡店（示例）", key="in_name")
            st.number_input("计算期（年）", 1, 30, 10, key="in_years")
            st.number_input("基准折现率（%)", 0.0, 50.0, 10.0, 0.5, key="in_rate")
            st.number_input("建设投资（元）", 0, 10_000_000, 320_000, 10_000, key="in_invest")
            st.number_input("流动资金（元）", 0, 10_000_000, 40_000, 10_000, key="in_wc")
        with c2:
            st.number_input("首年营业收入（元）", 0, 100_000_000, 650_000, 10_000, key="in_revenue")
            st.number_input("收入年增速（%)", -30.0, 100.0, 6.0, 1.0, key="in_growth")
            st.number_input("变动成本占收入比（%)", 0.0, 100.0, 36.0, 1.0, key="in_vcr")
            st.number_input("年固定经营成本（元）", 0, 10_000_000, 258_000, 10_000, key="in_fixed")
        c3, c4 = st.columns(2)
        with c3:
            st.number_input("折旧年限（年）", 1, 30, 5, key="in_dep_years")
            st.number_input("残值率（%)", 0.0, 100.0, 5.0, 1.0, key="in_salvage")
            st.number_input("所得税率（%)", 0.0, 100.0, 25.0, 1.0, key="in_tax")
        with c4:
            st.number_input("设计年销量（杯）", 1, 100_000_000, 130_000, 5_000, key="in_volume")
            st.number_input("平均单价（元/杯）", 0.01, 1000.0, 5.0, 0.1, key="in_price")


GLOSSARY = {
    "NPV 净现值": "把未来每年净现金流按基准折现率折算回今天再加总。NPV>0 → 值得做。",
    "IRR 内部收益率": "让 NPV 恰好为 0 的折现率，代表项目自身的'年化收益率'。IRR > 基准折现率 → 可行。",
    "投资回收期": "回本所需年数；动态口径考虑了资金时间价值，比静态更真实。",
    "盈亏平衡点": "收入低到哪条线刚好不赚不亏；低于它就开始亏损（经营安全边际）。",
    "敏感性分析": "参数 ±10%/±20% 时 NPV 波动多大；波动大的是关键变量，要重点盯住。",
    "三情景分析": "悲观/基准/乐观三套假设对比，回答'最坏能坏到哪、最好能好到哪'。",
}


def chart_cashflow(r: dict) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        x=r["periods"], y=r["ncf"], name="各年净现金流", marker_color="#4C78A8",
        hovertemplate="年份 %{x} 年<br>净现金流：%{y:,.0f} 元<extra></extra>",
    )
    fig.add_scatter(
        x=r["periods"], y=r["cumulative_ncf"], name="累计(静态)",
        mode="lines+markers", line=dict(color="#F58518", width=3),
        hovertemplate="年份 %{x} 年<br>累计(静态)：%{y:,.0f} 元<extra></extra>",
    )
    fig.add_scatter(
        x=r["periods"], y=r["discounted_cumulative"], name="累计(折现)",
        mode="lines+markers", line=dict(color="#54A24B", width=3, dash="dash"),
        hovertemplate="年份 %{x} 年<br>累计(折现)：%{y:,.0f} 元<extra></extra>",
    )
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    fig.update_layout(
        title=dict(text="逐年现金流与累计回本", x=0.0),
        xaxis_title=dict(text="年份 t（年）", standoff=18),
        yaxis_title=dict(text="金额（元）", standoff=10),
        height=500,
        hovermode="x unified",
        font=dict(size=14),
        # 大留白：底部给足空间，x 轴刻度不再贴边
        margin=dict(l=85, r=35, t=115, b=105),
        legend=dict(orientation="h", yanchor="bottom", y=1.05,
                    xanchor="left", x=0.02, font=dict(size=13)),
        bargap=0.25,
    )
    return fig


def chart_tornado(rows: list) -> go.Figure:
    labels = [r["label"] for r in rows]
    base = [r["minus20"] for r in rows]
    width = [r["plus20"] - r["minus20"] for r in rows]
    top = [r["plus20"] for r in rows]
    fig = go.Figure(go.Bar(
        orientation="h", y=labels, x=width, base=base, marker_color="#E45756",
        customdata=[[b, t] for b, t in zip(base, top)],
        hovertemplate=(
            "%{y}<br>NPV 变动范围：%{customdata[0]:,.0f} ~ %{customdata[1]:,.0f} 元"
            "<extra>敏感性分析</extra>"
        ),
        text=[f"{b / 10000:+.0f} ~ {t / 10000:+.0f} 万" for b, t in zip(base, top)],
        textposition="outside",
    ))
    fig.add_vline(x=0, line_dash="dot", line_color="gray")
    fig.update_layout(
        title=dict(text="敏感性：参数 ±20% 对 NPV 的影响", x=0.0),
        xaxis_title="NPV 变动（元）", height=360, showlegend=False,
        font=dict(size=14), margin=dict(l=30, r=60, t=90, b=80),
    )
    return fig


def chart_scenarios(scenarios: list) -> go.Figure:
    colors = {"悲观": "#E45756", "基准": "#F58518", "乐观": "#54A24B"}
    fig = go.Figure(go.Bar(
        x=[s["情景"] for s in scenarios],
        y=[s["npv"] for s in scenarios],
        marker_color=[colors[s["情景"]] for s in scenarios],
        hovertemplate="%{x}情景 NPV：%{y:,.0f} 元<extra>三情景对比</extra>",
        text=[f"{s['npv'] / 10000:,.0f} 万" for s in scenarios],
        textposition="outside",
    ))
    fig.update_layout(
        title=dict(text="三情景 NPV 对比", x=0.0),
        yaxis_title="NPV（元）", height=360, font=dict(size=14),
        margin=dict(l=85, r=35, t=90, b=80),
    )
    return fig


def tab_finance(r: dict) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("NPV 净现值", fmt_wan(r["npv"]))
    c2.metric("IRR 内部收益率", fmt_pct(r["irr"]))
    c3.metric("动态回收期", fmt_years(r["payback_dynamic"]))
    c4, c5, c6 = st.columns(3)
    c4.metric("静态回收期", fmt_years(r["payback_static"]))
    bep = r["bep"]
    if bep["bep_volume"]:
        c5.metric("盈亏平衡销量", f"{bep['bep_volume']:,.0f} 杯/年")
        c6.metric("盈亏平衡产能占比", fmt_pct(bep["bep_utilization"]))
    else:
        c5.metric("盈亏平衡收入", f"{bep['bep_revenue'] / 10000:,.0f} 万")
        c6.metric("——", "——")

    with st.expander("💡 这些指标是什么意思？"):
        for k, v in GLOSSARY.items():
            st.markdown(f"- **{k}**：{v}")

    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(chart_cashflow(r), width="stretch")
    with col_b:
        st.plotly_chart(chart_tornado(r["sensitivity"]), width="stretch")
    st.plotly_chart(chart_scenarios(r["scenarios"]), width="stretch")

    c1, c2 = st.columns([1, 2])
    with c1:
        df_s = pd.DataFrame(r["scenarios"])
        df_s["NPV(万元)"] = (df_s["npv"] / 10000).round(1)
        df_s["IRR"] = df_s["irr"].apply(fmt_pct)
        df_s["回收期"] = df_s["payback_dynamic"].apply(fmt_years)
        st.dataframe(df_s[["情景", "NPV(万元)", "IRR", "回收期"]], hide_index=True,
                     width="stretch")
    with c2:
        with st.expander("📋 各年现金流明细（含折旧与税）"):
            st.dataframe(pd.DataFrame(r["annual_table"]), hide_index=True,
                         width="stretch")

    with st.expander("⚖️ 测算口径与简化假设"):
        st.markdown(
            "- 全投资（融资前）口径：利息不单列；\n"
            "- 直线折旧：年折旧 = 建设投资×(1-残值率)÷折旧年限；\n"
            "- 亏损年不纳税、不结转亏损；收入按固定增速增长；\n"
            "- 盈亏平衡固定成本口径 = 固定经营成本 + 年折旧；\n"
            "- 期末回收流动资金 + 账面残值变现。"
        )


def get_llm() -> LLMClient | None:
    """会话级 LLM 客户端（懒加载，未配置返回 None)。"""
    if "llm_client" not in st.session_state:
        try:
            st.session_state.llm_client = LLMClient()
        except Exception:
            st.session_state.llm_client = None
    return st.session_state.llm_client


def get_kb() -> KnowledgeBase | None:
    """会话级知识库（依赖 Embedding，未配置返回 None)。"""
    if "kb" not in st.session_state:
        llm = get_llm()
        if llm is None:
            st.session_state.kb = None
        else:
            try:
                st.session_state.kb = KnowledgeBase(embed_fn=llm.embed_texts)
            except Exception:
                st.session_state.kb = None
    return st.session_state.kb


def _show_audit(audit) -> None:
    """统一展示 AI 审核意见列表。"""
    if audit:
        for i, a in enumerate(audit, 1):
            st.markdown(f"{i}. **{a.get('field')}**:{a.get('question')}"
                        f"→ 建议：{a.get('suggestion')}")
    else:
        st.info("(AI 未提出额外疑问）")


def _render_qcard(card: dict) -> None:
    """把质检卡渲染成界面上的折叠面板。"""
    icons = {"pass": "✅", "warn": "⚠️", "fail": "❌", "na": "➖", "info": "ℹ️"}
    line = (f"通过 {card['n_pass']} 项 ｜ 提示 {card['n_warn']} 项 ｜ "
            f"未过 {card['n_fail']} 项")
    st.markdown(f"**{line}**（机器客观检查；语义质量请人工判断）")
    for c in card["checks"]:
        st.markdown(f"- {icons.get(c['status'], '•')} **{c['name']}**：{c['detail']}")


def tab_ai_report(p: ProjectParams, r: dict) -> None:
    st.markdown("生成流程：**AI 假设审核 → 财务章节（代码生成）→ 市场/风险（AI 执笔）→ 结论（规则判定）**。")
    cfg_banner("llm")
    llm = get_llm()

    # 人机协作第一步：可先"仅审核"，让作者看到质疑、修改参数后再生成
    c1, c2 = st.columns([1, 2])
    with c1:
        audit_clicked = st.button("🧐 仅审核假设（约 5 秒）", disabled=llm is None)
    with c2:
        st.caption("先让 AI 质疑你的参数 → 回上方修改 → 再生成完整报告"
                   "（生成时会再次审核，并把意见写入报告附录）")
    if audit_clicked:
        with st.spinner("AI 正在审核你的假设……"):
            try:
                pipe = ReportPipeline(client=llm, kb=get_kb())
                st.session_state.audit_only = pipe.audit_assumptions(p)
                st.session_state.audit_err = None
            except Exception as e:
                st.session_state.audit_only = None
                st.session_state.audit_err = f"审核失败：{e}"
    if st.session_state.get("audit_err"):
        st.error(st.session_state.audit_err)
    if st.session_state.get("audit_only"):
        st.markdown("#### 🧐 AI 对当前假设的质疑")
        _show_audit(st.session_state.audit_only)
        st.caption("觉得有道理？回到顶部参数区修改，再点下方'生成完整报告'。")

    if st.button("🤖 生成完整可研报告（约 20~60 秒）", type="primary",
                 disabled=llm is None):
        with st.spinner("AI 正在撰写……（假设审核 → 市场 → 风险）"):
            try:
                kb = get_kb()
                had_kb = bool(kb and kb.chunk_count)  # 质检"引用"项的前提
                pipe = ReportPipeline(client=llm, kb=kb)
                out = pipe.generate(p)
                st.session_state.report = out
                st.session_state.report_err = None
                st.session_state.qcard = quality_card(out, had_kb)
                # 顺带生成 Word 版（存字节，供下载按钮使用）
                tmp = EXPORT_DIR / f"_report_tmp_{abs(hash(p.name))}.docx"
                markdown_to_docx(out["report_markdown"], tmp)
                st.session_state.report_docx = tmp.read_bytes()
            except Exception as e:
                st.session_state.report = None
                st.session_state.report_err = f"生成失败：{e}"

    if st.session_state.get("report_err"):
        st.error(st.session_state.report_err)

    out = st.session_state.get("report")
    if out:
        st.success(f"报告生成完毕（本次约消耗 {out['tokens_used']:,} tokens）")
        st.download_button("⬇️ 下载 Markdown 报告", out["report_markdown"],
                           file_name=f"可研报告_{p.name}.md", mime="text/markdown")
        if st.session_state.get("report_docx"):
            st.download_button(
                "⬇️ 下载 Word 版报告",
                data=st.session_state.report_docx,
                file_name=f"可研报告_{p.name}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        _qcard = st.session_state.get("qcard")
        if _qcard and _qcard.get("checks"):
            with st.expander("🧾 质检卡（客观检查）", expanded=True):
                _render_qcard(_qcard)
        with st.expander("🧐 AI 假设审核意见（人机协作第一步）", expanded=True):
            _show_audit(out["audit"])
        st.markdown(out["report_markdown"])


def tab_rag() -> None:
    st.markdown("上传研报 / 政策 / 项目资料（PDF、Word、Excel、txt、md），"
                "系统建立知识库后，可带引用问答；报告的市场/风险章节也会引用它。")
    cfg_banner("both")
    llm = get_llm()
    kb = get_kb()

    files = st.file_uploader("上传资料（可多选）", type=["pdf", "docx", "doc", "xlsx",
                              "pptx", "txt", "md", "markdown"], accept_multiple_files=True)

    if st.button("📚 解析并入知识库", disabled=kb is None) and files:
        errors, added = [], 0
        with st.spinner("解析与向量化中……"):
            for f in files:
                dest = UPLOAD_DIR / f.name
                dest.write_bytes(f.getbuffer())
                try:
                    n = kb.add_document(dest)
                    added += n
                except DocumentParseError as e:
                    errors.append(f"{f.name}：{e}")
        st.success(f"入库完成：新增 {added} 个文本块。")
        for e in errors:
            st.error(e)

    if kb is not None:
        st.caption(f"知识库状态：{len(kb.sources)} 份文档 / {kb.chunk_count} 个文本块"
                   f"（{', '.join(kb.sources) if kb.sources else '空'}）")

    question = st.text_input("❓ 输入问题（例如：这份材料里补贴政策怎么说的？）")
    if st.button("🔍 提问（带引用）", disabled=kb is None) and question and kb and kb.chunk_count:
        with st.spinner("检索并回答中……"):
            hits = kb.query(question, k=4)
            if not hits:
                st.info("知识库为空或未检索到相关内容，请先上传资料。")
                return
            ctx = "\n\n".join(
                f"[来源：{m.get('source')}｜{m.get('heading')}]\n{t[:500]}"
                for _s, m, t in hits
            )
            try:
                answer = llm.chat_text(
                    "你是行业分析师。只依据给定资料片段回答，资料不足时明确说明；"
                    "每条结论尽量标注对应 [来源]。",
                    f"问题：{question}\n\n资料片段:\n{ctx}",
                )
                st.markdown("### 回答\n" + answer)
            except Exception as e:
                st.error(f"回答失败：{e}")
        with st.expander("📎 检索命中的原文片段（引用依据）"):
            for score, m, t in hits:
                st.markdown(f"- **{m.get('source')}｜{m.get('heading')}**"
                            f"（相似度 {score:.2f})\n\n> {t[:500]}")


def render() -> None:
    st.set_page_config(page_title="FeasAI · 可研助手", page_icon="📊", layout="wide")
    # 报告正文统一宋体（用户要求）
    st.html("""
        <style>
          .stMarkdown, .stMarkdown p, .stMarkdown li,
          .stMarkdown td, .stMarkdown th, .stMarkdown strong,
          .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {
            font-family: 'SimSun', '宋体', 'Songti SC', serif !important;
          }
        </style>
    """)
    st.title("📊 FeasAI · 项目可行性研究 AI 助手")
    st.caption("财务引擎真算 + AI 辅助报告：数字由引擎计算，绝不 AI 编造。"
               "项目文档见 docs/；本项目为个人作品（AI 辅助开发）。")

    archive_controls()

    params_editor()

    try:
        r = analyze(build_params())
    except Exception as e:
        st.error(f"参数有误：{e}")
        return

    t1, t2, t3 = st.tabs(["① 财务测算", "② AI 可研报告", "③ 资料问答（RAG）"])
    with t1:
        tab_finance(r)
    with t2:
        tab_ai_report(build_params(), r)
    with t3:
        tab_rag()


if __name__ == "__main__":
    render()
