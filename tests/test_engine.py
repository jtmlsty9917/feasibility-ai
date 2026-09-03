"""财务引擎单元测试：用一道"手算例题"对照实现是否正确。

手算例题（n=3，税率=0 使折旧在现金中抵消，便于笔算）：
- 建设投资 1000（t=0），无流动资金，残值率 0，折旧 3 年直线；
- 每年收入 600（增速 0），变动成本率 0，固定成本 100 → EBITDA=500；
- 税率 0 → 年净现金流 NCF1..3 = EBITDA = 500；NCF0 = -1000。

手算结果：
- NPV@10% = -1000 + 500×(1/1.1 + 1/1.21 + 1/1.331) ≈ 243.43
- IRR：年金因子 = 1000/500 = 2.0 对应的折现率 ≈ 23.38%
- 静态回收期 = 2.0 年（累计现金流在第 2 年末恰好回本）
- 动态回收期 ≈ 2.35 年
- 盈亏平衡（固定成本=100+折旧333.33=433.33，单价0.6、变动成本率0）
  → 产量 = 433.33/0.6 ≈ 722.2 杯/年
"""
import math
import os
import sys

# 允许直接 `python tests/test_engine.py` 运行：把项目根目录加入模块搜索路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feasibility_ai.engine import analyze
from feasibility_ai.engine.models import ProjectParams
from feasibility_ai.engine.cashflow import build_cashflows
from feasibility_ai.engine.indicators import npv, irr, payback, breakeven

TOL = 1e-6


def example_params() -> ProjectParams:
    return ProjectParams(
        name="手算例题",
        industry="测试",
        calc_years=3,
        discount_rate=0.10,
        initial_investment=1000.0,
        working_capital=0.0,
        first_year_revenue=600.0,
        revenue_growth=0.0,
        variable_cost_rate=0.0,
        fixed_operating_cost=100.0,
        depreciation_years=3,
        salvage_rate=0.0,
        tax_rate=0.0,
        annual_volume=1000.0,
        unit_price=0.6,
    )


def test_cashflows_match_hand_calc():
    flows = build_cashflows(example_params())
    assert len(flows) == 4
    assert abs(flows[0] - (-1000.0)) < TOL
    for t in (1, 2, 3):
        assert abs(flows[t] - 500.0) < TOL


def test_npv_matches_hand_calc():
    flows = build_cashflows(example_params())
    expected = -1000.0 + 500.0 * (1 / 1.1 + 1 / 1.1 ** 2 + 1 / 1.1 ** 3)
    assert abs(npv(flows, 0.10) - expected) < TOL
    assert expected > 243.4 and expected < 243.5


def test_irr_roundtrip():
    flows = build_cashflows(example_params())
    r = irr(flows)
    assert r is not None
    assert abs(npv(flows, r)) < 1e-6
    # IRR ≈ 23.4%（年金因子 2.0 附近）
    assert r > 0.23 and r < 0.24


def test_payback_static_and_dynamic():
    flows = build_cashflows(example_params())
    assert abs(payback(flows) - 2.0) < TOL
    dyn = payback(flows, 0.10)
    assert dyn is not None
    assert abs(dyn - 2.3518) < 0.01


def test_breakeven_matches_hand_calc():
    p = example_params()
    dep = p.initial_investment * (1 - p.salvage_rate) / p.depreciation_years
    fixed_total = p.fixed_operating_cost + dep  # 100 + 333.33 = 433.33
    bep = breakeven(p)
    assert abs(bep["fixed_total"] - fixed_total) < TOL
    assert abs(bep["bep_volume"] - fixed_total / 0.6) < 0.01  # ≈722.2
    assert abs(bep["bep_utilization"] - (fixed_total / 0.6) / 1000.0) < 0.001


def test_analyze_end_to_end():
    res = analyze(example_params())
    assert res["npv"] > 0
    assert res["irr"] is not None
    assert res["irr"] > res["rate"]
    assert len(res["ncf"]) == 4
    assert len(res["annual_table"]) == 3
    assert len(res["sensitivity"]) == 5      # 5 个敏感参数
    assert len(res["scenarios"]) == 3        # 悲观/基准/乐观
    # 敏感性行已按影响幅度升序排序（最大的在最后）
    spreads = [r["spread"] for r in res["sensitivity"]]
    assert spreads == sorted(spreads)
    # 三情景 NPV 排序：悲观 < 基准 < 乐观
    npvs = [s["npv"] for s in res["scenarios"]]
    assert npvs[0] < npvs[1] < npvs[2]
    # 期末回收：无残值、无流动资金时不改变 t=3 现金流
    assert abs(res["ncf"][-1] - 500.0) < TOL


def test_bubble_tea_example_runs():
    """奶茶店示例应能跑通且 NPV 为正（演示时不会尴尬）。"""
    res = analyze(ProjectParams())
    assert math.isfinite(res["npv"])
    assert res["npv"] > 0
    assert res["irr"] is not None
    print(f"\n[奶茶店示例] NPV={res['npv']:,.0f} 元, IRR={res['irr']*100:.1f}%, "
          f"动态回收期={res['payback_dynamic']:.1f} 年, "
          f"盈亏平衡销量={res['bep']['bep_volume']:,.0f} 杯/年 "
          f"({res['bep']['bep_utilization']*100:.0f}% 产能)")


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    sys.exit(1 if failed else 0)
