"""analysis/actions.py — 行动清单状态流 + 效果回看对比。

五状态：待评估 → 处理中 → 待回看 → 已完成 / 已关闭。
首次生成行动项时自动把目标指标快照存入 SQLite（动作前基线）。
回看：导入新数据 → 对比动作前后同口径指标 → AI 生成摘要。
"""
from __future__ import annotations

import json
from typing import Any

from core import storage

STATUS_FLOW = ["待评估", "处理中", "待回看", "已完成", "已关闭"]
VALID_TRANSITIONS = {
    "待评估": ["处理中", "已关闭"],
    "处理中": ["待回看", "已关闭"],
    "待回看": ["已完成", "处理中"],
    "已完成": [],
    "已关闭": [],
}


def create_action(
    problem: str,
    evidence: str | None,
    priority: str,
    suggested_action: str,
    target_metric: str | None,
    review_time: str | None,
    baseline_snapshot: dict | None = None,
) -> int:
    """创建行动项，自动存入动作前指标快照。"""
    return storage.insert_action(
        problem=problem,
        evidence=evidence,
        priority=priority,
        suggested_action=suggested_action,
        target_metric=target_metric,
        review_time=review_time,
        snapshot=baseline_snapshot,
    )


def transition(action_id: int, to_status: str) -> tuple[bool, str]:
    """状态流转，校验合法性。"""
    actions = storage.list_actions()
    cur = next((a for a in actions if a["id"] == action_id), None)
    if cur is None:
        return False, "行动项不存在"
    from_status = cur["status"]
    allowed = VALID_TRANSITIONS.get(from_status, [])
    if to_status not in allowed:
        return False, f"不允许从「{from_status}」流转到「{to_status}」"
    storage.update_action_status(action_id, to_status)
    return True, ""


def review_action(
    action_id: int,
    new_snapshot: dict,
) -> dict:
    """回看：对比动作前后同口径指标，返回对比结果。

    返回 {指标: {动作前, 动作后, 差值}}。
    """
    actions = storage.list_actions()
    cur = next((a for a in actions if a["id"] == action_id), None)
    if cur is None:
        return {"error": "行动项不存在"}
    baseline = cur.get("snapshot") or {}
    if not baseline:
        return {"error": "无动作前快照，无法对比"}

    compare = {}
    for metric, before_val in baseline.items():
        after_val = new_snapshot.get(metric)
        if after_val is None:
            continue
        try:
            diff = float(after_val) - float(before_val)
        except (TypeError, ValueError):
            diff = None
        compare[metric] = {
            "动作前": before_val,
            "动作后": after_val,
            "差值": diff,
        }
    return compare


def snapshot_from_metrics(metrics: dict[str, float | int]) -> dict:
    """把指标结果转成快照（只保留可序列化的数值）。"""
    return {k: v for k, v in metrics.items() if isinstance(v, (int, float))}
