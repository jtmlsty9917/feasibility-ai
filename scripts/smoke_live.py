"""真实 API 冒烟测试：用 DeepSeek 真跑一遍"奶茶店 → 完整可研报告"。

用法：先在 .env 填好 LLM_API_KEY，然后运行：
    .venv\\Scripts\\python scripts\\smoke_live.py
输出：data/outputs/真实冒烟_report.md（+ .docx），控制台打印摘要。
安全：不回显 Key；失败时打印可读错误（余额不足/网络/格式）。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feasibility_ai.llm import LLMClient
from feasibility_ai.engine import ProjectParams
from feasibility_ai.workflow.report import ReportPipeline
from feasibility_ai.reports import markdown_to_docx

OUT_DIR = Path("data/outputs")


def main() -> int:
    if not os.getenv("LLM_API_KEY") or "PASTE" in os.getenv("LLM_API_KEY", ""):
        print("✗ 请先在 .env 填写 LLM_API_KEY（DeepSeek 真实 Key）")
        return 1

    scenario = sys.argv[1] if len(sys.argv) > 1 else "base"
    if scenario == "pessimistic":
        p = ProjectParams(
            name="奶茶店（悲观压力测试）",
            first_year_revenue=200_000.0,   # 收入远低于成本
            revenue_growth=0.0,
            fixed_operating_cost=300_000.0,
            initial_investment=400_000.0,
            working_capital=80_000.0,
        )
        print("使用悲观参数做压力测试：首年收入 20 万 / 固定成本 30 万 / 投资 48 万")
    else:
        p = ProjectParams()

    print("① 连接 DeepSeek 并开始生成（约 20~90 秒）……")
    t0 = time.time()
    try:
        client = LLMClient()
        pipe = ReportPipeline(client=client)  # 未配 Embedding：市场/风险无资料引用，属预期
        out = pipe.generate(p)
    except Exception as e:
        print(f"✗ 调用失败：{e}")
        print("  常见原因：余额不足 / Key 错误 / 网络不通 / 模型名不对。")
        return 1

    secs = time.time() - t0
    r = out["result"]

    # 摘要（不打印完整报告，太长）
    print(f"✓ 生成成功，耗时 {secs:.0f} 秒，消耗 {out['tokens_used']:,} tokens")
    print(f"✓ AI 假设审核提出 {len(out['audit'])} 个问题：")
    for i, a in enumerate(out["audit"], 1):
        print(f"   {i}. {a.get('field')}：{a.get('question')}")
    irr_txt = f"{r['irr'] * 100:.1f}%" if r["irr"] is not None else "不适用（现金流非常规，用 NPV 判据）"
    pb_txt = f"{r['payback_dynamic']:.2f} 年" if r["payback_dynamic"] is not None else "超出计算期"
    print(f"✓ 财务：NPV≈{r['npv'] / 10000:,.0f} 万 | IRR≈{irr_txt} | "
          f"动态回收期 {pb_txt}")
    print(f"✓ 市场章节 {len(out['sections']['二、市场分析'])} 字 | "
          f"风险章节 {len(out['sections']['四、风险分析与对策'])} 字")
    print("\n—— 市场章节开头 ——")
    print(out["sections"]["二、市场分析"][:300])
    print("\n—— 风险章节开头 ——")
    print(out["sections"]["四、风险分析与对策"][:300])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = "" if scenario == "base" else f"_{scenario}"
    md_path = OUT_DIR / f"真实冒烟{tag}_report.md"
    docx_path = OUT_DIR / f"真实冒烟{tag}_report.docx"
    md_path.write_text(out["report_markdown"], encoding="utf-8")
    markdown_to_docx(out["report_markdown"], docx_path)
    print(f"\n已保存：{md_path} 和 {docx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
