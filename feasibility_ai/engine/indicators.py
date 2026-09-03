"""核心评价指标：NPV / IRR / 回收期 / 盈亏平衡（纯函数，零依赖）。

公式出处：技术经济学 / 工程经济学教材（项目经济评价章节）。
每个函数都按"手算可验"的方式实现，单元测试用一道手算例题对照。
"""
from __future__ import annotations

from typing import List, Optional

from .models import ProjectParams
from .cashflow import annual_depreciation


def npv(flows: List[float], rate: float) -> float:
    """净现值 NPV = Σ NCF_t / (1+i)^t，t=0..n。

    判据：NPV ≥ 0 → 项目在基准收益率 i 下可行。
    """
    return sum(f / (1.0 + rate) ** t for t, f in enumerate(flows))


def irr(flows: List[float],
        lo: float = -0.9999, hi: float = 20.0,
        tol: float = 1e-9, max_iter: int = 300) -> Optional[float]:
    """内部收益率 IRR：使 NPV=0 的折现率（二分法数值求解）。

    说明：常规现金流（先负后正）只有一个 IRR；若区间两端 NPV 同号，
    说明无非寻常解（可能现金流非常规，出现多重 IRR），返回 None，
    界面提示"建议改用 NPV 判断"。
    """
    def f(r: float) -> float:
        return npv(flows, r)

    f_lo, f_hi = f(lo), f(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = f(mid)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid <= 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return (lo + hi) / 2.0


def payback(flows: List[float], rate: Optional[float] = None) -> Optional[float]:
    """投资回收期（年，线性插值到月）。

    - rate=None → 静态回收期（按未折现累计现金流）；
    - rate=i    → 动态回收期（按折现累计现金流）。
    计算期内未回收则返回 None（说明回收期超出计算期）。
    """
    cum = 0.0
    prev_cum = 0.0
    for t, f in enumerate(flows):
        value = f if rate is None else f / (1.0 + rate) ** t
        prev_cum = cum
        cum += value
        if cum >= 0 and t >= 1:
            if value <= 0:  # 防御：该年现金流非正但累计转正
                return float(t)
            return t - 1 + (-prev_cum) / value  # 线性插值
    return None


def breakeven(p: ProjectParams) -> dict:
    """盈亏平衡分析（产量口径 + 收入口径）。

    口径声明（面试用）：固定成本 = 年固定经营成本 + 年折旧（教材常用口径）；
    若想纯现金流口径可不含折旧 —— 本实现用含折旧口径并在界面注明。
    产量口径需要"销量×单价"假设：单位变动成本 = 单价 × 变动成本率。
    """
    dep = annual_depreciation(p)
    fixed_total = p.fixed_operating_cost + dep
    unit_variable = p.unit_price * p.variable_cost_rate  # 元/杯
    denom = p.unit_price - unit_variable

    bep_volume = None
    bep_utilization = None
    if denom > 0:
        bep_volume = fixed_total / denom
        if p.annual_volume > 0:
            bep_utilization = bep_volume / p.annual_volume

    # 收入口径（不依赖销量）：BEP_收入 = 固定成本 / 边际贡献率(1−变动成本率)
    bep_revenue = None
    if p.variable_cost_rate < 1.0:
        bep_revenue = fixed_total / (1.0 - p.variable_cost_rate)

    return {
        "fixed_total": fixed_total,
        "unit_price": p.unit_price,
        "unit_variable_cost": unit_variable,
        "bep_volume": bep_volume,          # 杯/年
        "bep_utilization": bep_utilization,  # 占设计产能比例
        "bep_revenue": bep_revenue,          # 元/年
    }
