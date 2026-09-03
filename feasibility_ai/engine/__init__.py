"""财务测算引擎：对外统一入口 analyze()。

设计原则（面试话术）：
1. 本模块是纯计算，绝不调用大模型 —— 所有数字只由公式算出；
2. 返回结构化的普通 dict，界面与报告共用同一份数据源，
   报告生成时从 JSON 注入数字，杜绝 LLM 编数。
"""
from __future__ import annotations

from .models import ProjectParams, from_dict, BUBBLE_TEA_EXAMPLE
from .cashflow import build_cashflows, annual_detail, annual_depreciation
from .indicators import npv, irr, payback, breakeven
from .sensitivity import sensitivity_table, run_scenarios


def analyze(p: ProjectParams) -> dict:
    """对项目参数做完整测算，返回可 JSON 序列化的结果字典。"""
    flows = build_cashflows(p)
    rate = p.discount_rate

    cumulative = []
    _acc = 0.0
    for f in flows:
        _acc += f
        cumulative.append(_acc)

    discounted_cumulative = []
    _acc = 0.0
    for t, f in enumerate(flows):
        _acc += f / (1.0 + rate) ** t
        discounted_cumulative.append(_acc)

    bep = breakeven(p)

    return {
        "project_name": p.name,
        "industry": p.industry,
        "rate": rate,
        "years": p.calc_years,
        "periods": list(range(p.calc_years + 1)),   # t=0..n
        "ncf": flows,                                # 各年净现金流
        "cumulative_ncf": cumulative,
        "discounted_cumulative": discounted_cumulative,
        "annual_table": annual_detail(p),
        "npv": npv(flows, rate),
        "irr": irr(flows),
        "payback_static": payback(flows),            # 静态回收期
        "payback_dynamic": payback(flows, rate),     # 动态回收期
        "bep": {
            **bep,
            "bep_daily": (bep["bep_volume"] / 365.0) if bep["bep_volume"] else None,
        },
        "sensitivity": sensitivity_table(p),
        "scenarios": run_scenarios(p),
        "depreciation_annual": annual_depreciation(p),
    }


__all__ = ["ProjectParams", "analyze", "from_dict", "BUBBLE_TEA_EXAMPLE"]
