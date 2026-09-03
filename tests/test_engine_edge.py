"""财务引擎边界用例：亏损年、期末回收、IRR 无解等（都是面试官爱追问的坑）。"""
import pytest

from feasibility_ai.engine.models import ProjectParams
from feasibility_ai.engine.cashflow import build_cashflows
from feasibility_ai.engine.indicators import npv, irr

TOL = 1e-6


def test_loss_year_pays_no_tax():
    """EBITDA 为负的年份：不纳税，NCF = EBITDA（亏损不结转的简化口径）。"""
    p = ProjectParams(
        calc_years=2,
        initial_investment=0.0,        # 无投资 → 无折旧
        working_capital=0.0,
        first_year_revenue=100_000.0,  # 收入远低于成本
        revenue_growth=0.0,
        variable_cost_rate=0.3,
        fixed_operating_cost=200_000.0,
        tax_rate=0.25,
    )
    flows = build_cashflows(p)
    ebitda = 100_000 - 30_000 - 200_000  # = -130,000
    assert flows[1] == pytest.approx(ebitda, abs=1e-6)  # 无税、无折旧
    assert flows[2] == pytest.approx(ebitda, abs=1e-6)


def test_terminal_recovery_of_wc_and_salvage():
    """期末应回收流动资金 + 账面残值；用恒定现金流验证差值。"""
    p = ProjectParams(
        calc_years=2,
        initial_investment=500_000.0,
        working_capital=80_000.0,
        first_year_revenue=600_000.0,
        revenue_growth=0.0,            # 恒定 → 折旧期内各年经营 NCF 相同
        variable_cost_rate=0.5,
        fixed_operating_cost=100_000.0,
        depreciation_years=5,          # 5 年 > 计算期 2 年 → 两年都提折旧
        salvage_rate=0.1,
        tax_rate=0.0,                  # 免税 → NCF = EBITDA（与折旧无关），便于手算
    )
    flows = build_cashflows(p)
    # 经营 NCF（第 1、2 年相同）：EBITDA = 600000-300000-100000 = 200000
    assert flows[1] == pytest.approx(200_000.0, abs=TOL)
    expected_terminal_add = p.working_capital + p.initial_investment * p.salvage_rate
    assert flows[2] - flows[1] == pytest.approx(expected_terminal_add, abs=TOL)


def test_irr_none_when_all_cashflows_positive():
    """全正现金流不存在使 NPV=0 的折现率 → 应返回 None 而非报错。"""
    assert irr([100.0, 100.0, 100.0]) is None


def test_irr_none_when_loss_everywhere():
    """全程亏损（现金流全负）同样无 IRR 解。"""
    p = ProjectParams(
        calc_years=3,
        first_year_revenue=50_000.0,
        revenue_growth=0.0,
        variable_cost_rate=0.5,
        fixed_operating_cost=300_000.0,
        initial_investment=0.0,
        working_capital=0.0,
    )
    flows = build_cashflows(p)
    # 无投资 → t=0 为 0；经营各年全为负 → 不存在 IRR 解
    assert all(f <= 0 for f in flows)
    assert any(f < 0 for f in flows)
    assert irr(flows) is None


def test_npv_hand_calc_again():
    """NPV 手算再校验（防回归）。"""
    flows = [-1000, 500, 500, 500]
    expected = -1000 + 500 * (1 / 1.1 + 1 / 1.1 ** 2 + 1 / 1.1 ** 3)
    assert npv(flows, 0.1) == pytest.approx(expected, abs=TOL)
