"""项目档案模块测试：存档/列表/读取/删除/名称安全。"""
import json

import pytest

from feasibility_ai.archive import (
    save_project,
    list_projects,
    load_project,
    delete_project,
    _slug,
)


def test_save_and_list_order(tmp_path):
    save_project(tmp_path, "奶茶店A", {"a": 1})
    save_project(tmp_path, "奶茶店B", {"b": 2})
    items = list_projects(tmp_path)
    assert len(items) == 2
    # 新的在前
    assert items[0]["name"] == "奶茶店B"
    assert items[1]["name"] == "奶茶店A"
    assert items[0]["params"] == {"b": 2}


def test_save_roundtrip_params(tmp_path):
    params = {"first_year_revenue": 650000.0, "discount_rate": 0.1}
    save_project(tmp_path, "示例项目", params)
    items = list_projects(tmp_path)
    data = load_project(tmp_path, items[0]["file"])
    assert data["params"] == params
    assert data["name"] == "示例项目"


def test_slug_safe():
    assert _slug("学校旁奶茶店（示例）!") == "学校旁奶茶店_示例"
    assert len(_slug("很" * 100)) <= 40


def test_list_empty_dir(tmp_path):
    assert list_projects(tmp_path) == []


def test_delete(tmp_path):
    save_project(tmp_path, "待删", {})
    items = list_projects(tmp_path)
    assert len(items) == 1
    delete_project(tmp_path, items[0]["file"])
    assert list_projects(tmp_path) == []


def test_corrupted_file_skipped(tmp_path):
    (tmp_path / "broken.json").write_text("not json", encoding="utf-8")
    save_project(tmp_path, "正常项目", {})
    items = list_projects(tmp_path)
    assert len(items) == 1
    assert items[0]["name"] == "正常项目"
