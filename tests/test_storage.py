"""tests/test_storage.py — 存储层与行动清单测试。"""
from __future__ import annotations

import pytest

from core import storage
from analysis import actions as act


@pytest.fixture(autouse=True)
def _init_db(tmp_path, monkeypatch):
    """每个测试用独立临时数据库。"""
    import core.config as cfg
    monkeypatch.setattr(cfg, "DB_PATH", tmp_path / "test.sqlite")
    storage.init_db()
    yield


def test_insert_and_list_action():
    aid = act.create_action(
        problem="识别成功率低",
        evidence="识别成功率 60%",
        priority="P1",
        suggested_action="补充同义问法",
        target_metric="识别成功率(%)",
        review_time="2026-09-01",
    )
    actions = storage.list_actions()
    assert any(a["id"] == aid for a in actions)


def test_status_flow():
    aid = act.create_action("问题", "证据", "P1", "动作", "指标", None)
    ok, msg = act.transition(aid, "处理中")
    assert ok is True
    # 待评估 -> 处理中 合法
    # 处理中 -> 待回看 合法
    ok2, _ = act.transition(aid, "待回看")
    assert ok2 is True
    # 已完成 -> 不可再流转
    storage.update_action_status(aid, "已完成")
    ok3, msg3 = act.transition(aid, "处理中")
    assert ok3 is False


def test_invalid_transition():
    aid = act.create_action("问题", "证据", "P1", "动作", "指标", None)
    # 待评估 不能直接到 已完成
    ok, msg = act.transition(aid, "已完成")
    assert ok is False


def test_review_without_snapshot():
    aid = act.create_action("问题", "证据", "P1", "动作", "指标", None)
    result = act.review_action(aid, {"识别成功率(%)": 80})
    assert "error" in result


def test_review_with_snapshot():
    aid = act.create_action(
        "问题", "证据", "P1", "动作", "指标", None,
        baseline_snapshot={"识别成功率(%)": 60},
    )
    result = act.review_action(aid, {"识别成功率(%)": 80})
    assert "error" not in result
    assert result["识别成功率(%)"]["差值"] == 20.0
