"""项目档案（记忆系统-第一版）：把项目参数存档到本地 JSON，重启不丢。

设计说明：
- 每个档案 = 一个 JSON 文件（data/projects/<时间戳>_<项目名>.json）；
- 内容：保存时间、项目名、全部参数（engine.ProjectParams 的 asdict 格式，小数域）；
- 提供 list / save / load 三个纯函数，与界面解耦，便于单元测试；
- 界面层负责"参数 ↔ 表单控件"的换算（见 app.py），本模块只管存取。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

DEFAULT_DIR = Path("data/projects")


def _slug(name: str) -> str:
    """把项目名转成安全的文件名片段（保留中文、字母数字，其余变下划线）。"""
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", name).strip("_")
    return s[:40] or "project"


def save_project(project_dir: str | Path, name: str, params: dict,
                 extra: dict | None = None) -> Path:
    """把项目参数存成一个档案文件，返回文件路径。同名会另存新档（可回溯）。"""
    d = Path(project_dir)
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "name": name,
        "params": params,
        "extra": extra or {},
    }
    file = d / f"{now}_{_slug(name)}.json"
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return file


def list_projects(project_dir: str | Path) -> list[dict]:
    """列出全部档案（新的在前）。每条含 file/saved_at/name/params。"""
    d = Path(project_dir)
    if not d.exists():
        return []
    items = []
    for f in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items.append({
                "file": f.name,
                "saved_at": data.get("saved_at", ""),
                "name": data.get("name", f.stem),
                "params": data.get("params", {}),
                "extra": data.get("extra", {}),
            })
        except (json.JSONDecodeError, OSError):
            continue  # 损坏的档案跳过，不影响其余
    return items


def load_project(project_dir: str | Path, file_name: str) -> dict:
    """按文件名读取单个档案；不存在时抛 FileNotFoundError。"""
    data = json.loads((Path(project_dir) / file_name).read_text(encoding="utf-8"))
    data["file"] = file_name
    return data


def delete_project(project_dir: str | Path, file_name: str) -> None:
    """删除一个档案（谨慎使用）。"""
    p = Path(project_dir) / file_name
    if p.exists():
        p.unlink()
