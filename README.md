# FeasAI · 项目可行性研究 AI 助手

> 状态：M1~M3 完成，**真实 API 冒烟已通过**（DeepSeek 实测：24 秒/2,364 tokens，
> 41 项单测全绿，含项目档案记忆系统与客观质检卡，详见 docs/smoke-report.md）
> ｜进行中：作者试玩反馈与 M4（git 提交/GitHub/录屏演示/简历定稿）（2026-09）
> ｜本人作品，AI 辅助开发（Agent 写码，作者负责产品设计与验收）
> 求职叙事：面向「产品经理 / AI 产品 / 运营综合岗」的作品集项目，代码量适中、业务内核来自作者专业（技术经济及管理）。

一句话定位：**输入一个项目想法或资料包，输出带真实财务测算、图表与引用来源的《项目可行性研究报告》，并支持对报告与资料追问。**

为什么不是"又一个聊天机器人"：财务结论（NPV/IRR/回收期/盈亏平衡/敏感性）由**自研 Python 财务引擎真算**，大模型只负责文本生成与解读，禁止编造数字 —— 这是本项目与通用 AI 产品最大的差异点。

## 快速开始

```powershell
# 1) 一次性准备（已完成）
py -3.10 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2) 无需 API Key 就能做的事
.venv\Scripts\python scripts\make_offline_preview.py   # 生成离线样例报告 → data/outputs/
.venv\Scripts\streamlit run app.py                     # 打开界面（① 财务测算离线可用）

# 3) 开启 AI 功能（②报告 ③问答）：复制 .env.example 为 .env，填入 DeepSeek + 硅基流动 Key

# 4) 配好 Key 后做真实冒烟（约 30 秒，验证整条 AI 链路）
.venv\Scripts\python scripts\smoke_live.py
```

> 界面说明：① 财务测算（改参数即重算）；② AI 可研报告（一键生成 + Word 导出）；
> ③ 资料问答（上传研报/政策 → 带引用问答）。测试：`.venv\Scripts\python -m pytest tests -q`

---

## 目录结构

```
feasibility-ai/
├── app.py                    # Streamlit 主界面（MVP 入口）
├── scripts/
│   └── make_offline_preview.py  # 离线生成样例报告（无需 API Key）
├── feasibility_ai/
│   ├── engine/               # 财务测算引擎（纯 Python，自研核心，无 LLM 依赖）
│   ├── knowledge/            # 文档解析、切块、向量检索（借鉴 RAGFlow 思路的简化实现）
│   ├── llm/                  # 大模型客户端（国内 API，OpenAI 兼容协议）
│   ├── workflow/             # 可研报告生成编排（假设审核 → 分析 → 编写 → 审查）
│   └── reports/              # 报告章节模板、Markdown → Word 导出
├── data/                     # 示例数据、样例行业资料（data/samples）
├── docs/
│   ├── PRD-v0.1.md           # 产品需求文档（为什么做、给谁用、做什么）
│   ├── architecture.md       # 技术架构与关键决策（含借鉴的开源生态与许可）
│   ├── milestones.md         # 里程碑、验收清单与"你要看懂什么"
│   ├── demo-script.md        # 10 分钟演示脚本（面试/录屏用）
│   ├── interview-qa.md       # 面试 QA 清单（业务/财务/架构/合规）
│   ├── resume-bullets.md     # 简历条目草稿与"AI 辅助开发"话术
│   ├── smoke-report.md       # 真实 API 冒烟记录（AI 链路可用的证据）
│   └── deployment.md         # 部署方案（本机录屏 / 云服务器）
├── tests/
├── requirements.txt
├── .env.example              # 大模型 API Key 配置模板
└── README.md
```

## 借力的高星开源生态（合规二创：依赖 / 借鉴思路，不抄代码）

| 开源项目 | 用法 | 许可 |
|---|---|---|
| microsoft/markitdown | PDF/Word/Excel → Markdown 文本（第三方依赖） | MIT |
| RAGFlow | 借鉴"文档解析 + 知识库问答"思路（简化自实现） | 学思路 |
| OpenAI Agents SDK / LangGraph | 参考多角色编排思想（MVP 用原生 Python 编排） | 学思路 |
| Streamlit / Plotly | 演示界面与图表 | Apache-2.0 / MIT |
| 自研向量检索 | numpy 余弦 top-k（约 100 行，接口可平滑换 chroma/FAISS） | 自研 |
| NextChat / LobeChat | 仅参考交互设计 | 参考 UI |

自研（简历与面试主菜）：财务测算引擎、可研报告工作流、假设审核的人机协作机制、领域知识库 schema、全套业务文档。

## 里程碑（详见 docs/milestones.md）

M0 环境与骨架 → M1 财务引擎 MVP（先不接 LLM）→ M2 接入大模型（报告 + 问答）→ M3 打磨与导出 → M4 部署与简历包装。

## 学习路径（作者目标：看得懂、讲得出）

1. 先读 `docs/architecture.md` 的架构图与数据流，建立全局；
2. 每完成一个里程碑，做一次"验收 + 面试三句话"自测（清单在 milestones.md）；
3. 重点精读 `engine/` 里的公式实现（有中文注释），其余模块知道"干什么、为什么"即可。
