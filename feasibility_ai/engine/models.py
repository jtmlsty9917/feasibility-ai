"""项目参数模型（M1 完整版）。

财务口径（重要，注释即"面试讲法"）：
- 采用"全投资（融资前）口径"：不区分资本金与贷款，利息不单列（MVP 简化，
  后续 P2 可扩展资本金现金流量表）；
- 直线折旧：年折旧 = 建设投资 × (1 − 残值率) / 折旧年限；
- 企业所得税按"利润总额 > 0"计，亏损年不纳税、不结转亏损（简化假设，注释注明）；
- 期末回收：流动资金全额回收 + 残值按账面残值变现。

所有金额单位：元；时间轴：t=0 为投资时点，t=1..calc_years 为经营年份。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields


@dataclass
class ProjectParams:
    # ---------- 基本信息 ----------
    name: str = "学校旁奶茶店（示例）"
    industry: str = "餐饮零售"
    calc_years: int = 10          # 计算期（年）：t=1..calc_years 为经营年份
    discount_rate: float = 0.10   # 基准折现率 i（要求收益率/资金成本，10%）

    # ---------- 投资 ----------
    initial_investment: float = 320_000.0  # 建设投资（装修+设备+开办/转让费，t=0 一次性）
    working_capital: float = 40_000.0      # 流动资金（t=0 垫付，期末回收）

    # ---------- 收入与成本 ----------
    first_year_revenue: float = 650_000.0  # 首年营业收入（≈130,000杯 × 均价5元）
    revenue_growth: float = 0.06           # 年收入增速（简化：全程恒定增速）
    variable_cost_rate: float = 0.36       # 变动成本 / 收入（食材、包装、平台抽成等）
    fixed_operating_cost: float = 258_000.0  # 年固定经营成本（房租+人工+水电等，不含折旧/利息）

    # ---------- 折旧与税 ----------
    depreciation_years: int = 5            # 直线折旧年限
    salvage_rate: float = 0.05             # 残值率（按建设投资）
    tax_rate: float = 0.25                 # 企业所得税率

    # ---------- 盈亏平衡（产量口径，可选）----------
    annual_volume: float = 130_000.0       # 设计年销量（杯），与首年收入口径一致（130,000×5元）
    unit_price: float = 5.0                # 平均单价（元/杯）

    # ---------- 场景乘数（敏感性/情景分析用）----------
    scenario_optimistic: float = 1.15      # 乐观：收入上浮
    scenario_pessimistic: float = 0.85     # 悲观：收入下浮


# 奶茶店示例的推荐默认值（与 PRD F0-6 一致：60㎡级、建设投资 32 万 + 流动资金 4 万、
# 首年收入 65 万。口径说明：基准假设偏乐观（未计店主个人薪酬），
# 这正是 M2"假设审核"会主动质疑的点，可配合敏感性/悲观情景看风险。）
BUBBLE_TEA_EXAMPLE: dict = asdict(ProjectParams())


def from_dict(d: dict) -> ProjectParams:
    """用字典构造参数（前端表单 / 测试共用），未知字段忽略。"""
    known = {f.name for f in fields(ProjectParams)}
    return ProjectParams(**{k: v for k, v in d.items() if k in known})


__all__ = ["ProjectParams", "BUBBLE_TEA_EXAMPLE", "from_dict"]
