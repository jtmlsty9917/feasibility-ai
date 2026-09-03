"""现金流构建：把项目参数变成逐年净现金流序列（纯函数，无依赖）。

时间轴约定（与 models.py 一致）：
- t=0：投入 建设投资 + 流动资金 → 净现金流为负；
- t=1..calc_years：经营年份，计算 收入→变动成本→固定成本→EBITDA→折旧→税；
- t=calc_years 末：回收流动资金 + 残值（按账面残值变现）。

现金流口径（供面试讲解）：
- 全投资口径：利息不单列、融资不影响 NCF（评估"项目本身"是否值得做）；
- 税盾表达：NCF = (利润总额)(1−税率) + 折旧 = EBITDA×(1−税率) + 折旧×税率；
- 简化假设（注释即口径声明，避免被挑战）：亏损年不纳税、不结转亏损；
  收入全程按固定增速增长（不做爬坡期/平稳期分段）。
"""
from __future__ import annotations

from typing import List

from .models import ProjectParams


def annual_depreciation(p: ProjectParams) -> float:
    """直线折旧：年折旧 = 建设投资 × (1 − 残值率) / 折旧年限。"""
    if p.depreciation_years <= 0:
        return 0.0
    return p.initial_investment * (1.0 - p.salvage_rate) / p.depreciation_years


def revenue_in_year(p: ProjectParams, t: int) -> float:
    """第 t 年营业收入：首年收入按固定增速增长（t≥1）。"""
    return p.first_year_revenue * (1.0 + p.revenue_growth) ** (t - 1)


def build_cashflows(p: ProjectParams) -> List[float]:
    """返回长度为 calc_years+1 的净现金流列表，索引 0..calc_years 对应 t=0..n。"""
    dep_annual = annual_depreciation(p)
    flows: List[float] = []
    flows.append(-(p.initial_investment + p.working_capital))  # t=0

    for t in range(1, p.calc_years + 1):
        rev = revenue_in_year(p, t)
        variable = rev * p.variable_cost_rate
        ebitda = rev - variable - p.fixed_operating_cost  # 未计折旧与税的经营利润
        dep = dep_annual if t <= p.depreciation_years else 0.0
        profit_base = ebitda - dep  # 利润总额（应税口径，简化：无纳税调整项）
        tax = max(profit_base, 0.0) * p.tax_rate  # 亏损年不纳税（简化）
        ncf = (profit_base - tax) + dep  # 等价于 profit_base×(1−t) + dep

        if t == p.calc_years:  # 期末：回收流动资金 + 账面残值
            ncf += p.working_capital + p.initial_investment * p.salvage_rate

        flows.append(ncf)

    return flows


def annual_detail(p: ProjectParams) -> List[dict]:
    """逐年明细（收入/成本/折旧/税/净现金流），供界面表格展示。"""
    dep_annual = annual_depreciation(p)
    rows = []
    for t in range(1, p.calc_years + 1):
        rev = revenue_in_year(p, t)
        variable = rev * p.variable_cost_rate
        fixed = p.fixed_operating_cost
        ebitda = rev - variable - fixed
        dep = dep_annual if t <= p.depreciation_years else 0.0
        profit_base = ebitda - dep
        tax = max(profit_base, 0.0) * p.tax_rate
        ncf = (profit_base - tax) + dep
        if t == p.calc_years:
            ncf += p.working_capital + p.initial_investment * p.salvage_rate
        rows.append({
            "年度": t,
            "营业收入": round(rev, 2),
            "变动成本": round(variable, 2),
            "固定成本": round(fixed, 2),
            "EBITDA": round(ebitda, 2),
            "折旧": round(dep, 2),
            "所得税": round(tax, 2),
            "净现金流NCF": round(ncf, 2),
        })
    return rows
