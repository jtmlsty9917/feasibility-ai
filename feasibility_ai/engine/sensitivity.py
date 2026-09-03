"""不确定性与风险分析：单因素敏感性 + 三情景（纯函数，零依赖）。

- 敏感性：对关键参数做 ±10% / ±20% 扰动，观察 NPV 变化幅度，
  变化越大的参数越是"关键变量"（风险管控重点）；
- 情景：悲观 / 基准 / 乐观三套假设下的 NPV、IRR、回收期对比。
"""
from __future__ import annotations

from typing import List

from dataclasses import replace

from .models import ProjectParams
from .cashflow import build_cashflows
from .indicators import npv, irr, payback


def _npv_of(p: ProjectParams) -> float:
    return npv(build_cashflows(p), p.discount_rate)


def sensitivity_table(p: ProjectParams) -> List[dict]:
    """返回 tornado 图数据行：每个关键参数 ±10/±20% 的 NPV 变化。

    行结构：{label, minus20, minus10, plus10, plus20, spread}，spread 越大越关键。
    """
    baseline = _npv_of(p)

    # (标签, 参数名, 乘数作用于 base 后与 base 之差)
    factors = [
        ("首年收入", "first_year_revenue", lambda b: b),
        ("变动成本率", "variable_cost_rate", lambda b: b),
        ("固定经营成本", "fixed_operating_cost", lambda b: b),
        ("建设投资", "initial_investment", lambda b: b),
        ("基准折现率", "discount_rate", lambda b: b),
    ]

    rows = []
    for label, attr, _transform in factors:
        base_val = getattr(p, attr)
        deltas = {}
        for delta in (-0.20, -0.10, 0.10, 0.20):
            new_p = replace(p, **{attr: base_val * (1.0 + delta)})
            deltas[delta] = _npv_of(new_p) - baseline
        rows.append({
            "label": label,
            "minus20": deltas[-0.20],
            "minus10": deltas[-0.10],
            "plus10": deltas[0.10],
            "plus20": deltas[0.20],
            "spread": abs(deltas[-0.20] - deltas[0.20]),
        })

    rows.sort(key=lambda r: r["spread"])
    return rows


def run_scenarios(p: ProjectParams) -> List[dict]:
    """三情景对比：对收入/成本做乘数调整后重算指标。"""
    p_opt = replace(
        p,
        first_year_revenue=p.first_year_revenue * p.scenario_optimistic,
        variable_cost_rate=min(p.variable_cost_rate - 0.05, 0.0 + 0.90),
        fixed_operating_cost=p.fixed_operating_cost * 0.90,
    )
    p_pes = replace(
        p,
        first_year_revenue=p.first_year_revenue * p.scenario_pessimistic,
        variable_cost_rate=p.variable_cost_rate + 0.05,
        fixed_operating_cost=p.fixed_operating_cost * 1.10,
    )

    def _metrics(pp: ProjectParams) -> dict:
        flows = build_cashflows(pp)
        return {
            "npv": npv(flows, pp.discount_rate),
            "irr": irr(flows),
            "payback_dynamic": payback(flows, pp.discount_rate),
        }

    base = _metrics(p)
    return [
        {"情景": "悲观", **_metrics(p_pes)},
        {"情景": "基准", **base},
        {"情景": "乐观", **_metrics(p_opt)},
    ]
