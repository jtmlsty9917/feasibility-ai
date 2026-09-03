# 部署与演示方案（M4 用，先到先选）

> 目标：让面试官/导师能访问到演示，两种档位任选。
> 前提结论：作者本机暂无 Docker；本项目纯 Python 可跑，**不依赖 Docker**。

## 方案 A：本机录屏演示（0 成本，推荐先用）

适合：简历投递阶段、视频面试。10 分钟录屏按 `docs/demo-script.md` 走。

```powershell
.venv\Scripts\streamlit run app.py   # 本机 http://localhost:8501
# 录屏工具：Windows 自带 Win+G（Xbox Game Bar）或 OBS
```

**产出物**：`演示录屏.mp4`（5~10 分钟）+ GitHub 仓库链接 + README 截图。

## 方案 B：云服务器部署（对外可访问 URL，~¥100/年）

### 1. 采购（学生优惠）
- 阿里云/腾讯云**轻量应用服务器**，2C2G 即可（约 ¥100/年，学生认证后更低）；
- 系统选 **Ubuntu 22.04**；地域选国内需域名备案（约 1~2 周），
  赶时间可选中国香港地域免备案（延迟稍高）。

### 2. 服务器上装环境
```bash
sudo apt update && sudo apt install -y python3.10-venv git
git clone <你的 GitHub 仓库地址> feasibility-ai && cd feasibility-ai
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env        # 填入真实 Key
```

### 3. 用 systemd 常驻（替代 pm2/宝塔，少装东西）
创建 `/etc/systemd/system/feasai.service`：
```ini
[Unit]
Description=FeasAI streamlit
After=network.target

[Service]
WorkingDirectory=/root/feasibility-ai
ExecStart=/root/feasibility-ai/.venv/bin/streamlit run app.py \
    --server.address 0.0.0.0 --server.port 8501 --server.headless true
Restart=always
EnvironmentFile=/root/feasibility-ai/.env

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now feasai
```

### 4. 访问与安全
- 云厂商控制台放行 8501 端口；直接 `http://<公网IP>:8501` 可访问；
- 后续可选：域名 + nginx 反代 + HTTPS（Let's Encrypt）；
- ⚠️ MVP 无登录鉴权，**演示完建议关停**或加简单密码（P1 项）。

## 方案 C：一键脚本（B 方案自动化）
到 M4 如需，我提供 `scripts/deploy.sh`（装依赖+建 service）和
`scripts/deploy.ps1`（本机 Docker 备选）。作者本机无 Docker，默认走 A/B。

## 上线前检查清单
- [ ] `pytest tests -q` 全绿
- [ ] `.env` 真实 Key 冒烟通过（报告能生成、问答有引用）
- [ ] README 截图 3 张：测算页 / 报告页 / 问答页
- [ ] GitHub 仓库公开 + commit 历史干净（.env 不入库）
- [ ] 录屏 5~10 分钟（demo-script.md 为台本）
