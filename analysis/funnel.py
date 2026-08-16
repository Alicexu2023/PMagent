"""analysis/funnel.py — 漏斗分析。

默认链路：进入智能体 → 发起提问 → 获得有效回答 → 点击推荐/下一步 → 完成业务动作。
步骤可自定义。展示各步人数、转化率、流失率，支持按问题类型/用户属性下钻。
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from core import config


# 默认漏斗步骤定义：步骤名 -> 匹配的 event_name 关键词（小写包含匹配）
DEFAULT_FUNNEL_STEPS = [
    ("进入智能体", ["enter", "进入", "open", "启动", "start", "visit", "打开"]),
    ("发起提问", ["ask", "提问", "question", "query", "问"]),
    ("获得有效回答", ["answer", "回答", "reply", "回复", "response"]),
    ("点击推荐/下一步", ["click", "点击", "recommend", "推荐", "next", "下一步"]),
    ("完成业务动作", ["complete", "完成", "submit", "提交", "order", "下单", "done", "业务"]),
]


def _match_event(event_name: str, keywords: list[str]) -> bool:
    e = str(event_name).lower()
    return any(k.lower() in e for k in keywords)


def funnel_analysis(
    df: pd.DataFrame,
    steps: list[tuple[str, list[str]]] | None = None,
    user_col: str = "user_id",
    event_col: str = "event_name",
) -> pd.DataFrame:
    """计算漏斗各步达标用户数、转化率、流失率。

    返回列：步骤、达标用户数、转化率(%)、流失率(%)。
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if event_col not in df.columns or user_col not in df.columns:
        return pd.DataFrame()

    steps = steps or DEFAULT_FUNNEL_STEPS
    d = df.copy()
    d[event_col] = d[event_col].astype(str)

    rows = []
    prev_users: set[str] | None = None
    for name, keywords in steps:
        matched = d[d[event_col].apply(lambda e: _match_event(e, keywords))]
        users = set(matched[user_col].astype(str).tolist()) if user_col in d.columns else set()
        conv = (len(users) / len(prev_users) * 100) if prev_users else None
        # 流失率 = 1 - 转化率（相对上一步）
        churn = (100 - conv) if conv is not None else None
        rows.append({
            "步骤": name,
            "达标用户数": len(users),
            "转化率(%)": round(conv, 2) if conv is not None else 100.0,
            "流失率(%)": round(churn, 2) if churn is not None else 0.0,
        })
        prev_users = users

    return pd.DataFrame(rows)


def funnel_drilldown(
    df: pd.DataFrame,
    step_name: str,
    steps: list[tuple[str, list[str]]] | None = None,
    by: str = "recognized_intent",
    event_col: str = "event_name",
    user_col: str = "user_id",
) -> pd.DataFrame:
    """漏斗某步流失下钻：按问题类型/用户属性分布。

    by 可选：recognized_intent（问题类型）或用户属性列名。
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if event_col not in df.columns or user_col not in df.columns:
        return pd.DataFrame()

    steps = steps or DEFAULT_FUNNEL_STEPS
    # 找到该步的达标用户
    step_users: set[str] = set()
    target_keywords = None
    for name, keywords in steps:
        if name == step_name:
            target_keywords = keywords
            break
    if target_keywords is None:
        return pd.DataFrame()

    d = df.copy()
    d[event_col] = d[event_col].astype(str)
    matched = d[d[event_col].apply(lambda e: _match_event(e, target_keywords))]
    step_users = set(matched[user_col].astype(str).tolist())

    # 下钻维度：优先 by 列，缺失则回退 event_name
    if by not in d.columns:
        by = event_col
    sub = d[d[user_col].astype(str).isin(step_users)]
    dist = sub.groupby(by).size().reset_index(name="人数")
    dist = dist.sort_values("人数", ascending=False).reset_index(drop=True)
    return dist
