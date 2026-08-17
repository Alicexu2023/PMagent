"""analysis/paths.py — 路径分析。

分析用户提问前来源页面/前置操作，提问后的后续页面/业务动作/退出位置。
默认前后各 5 步，支持排除噪声事件（曝光、心跳、系统噪声）。
Top 路径按（用户, 会话）去重后的路径序列频次降序。
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from core import config

# 噪声事件关键词（默认排除）
NOISE_KEYWORDS = ["曝光", "心跳", "heartbeat", "expose", "impression", "系统", "system", "ping", "noise"]


def _is_noise(event_name: str, extra_noise: list[str] | None = None) -> bool:
    e = str(event_name).lower()
    kws = NOISE_KEYWORDS + (extra_noise or [])
    return any(k.lower() in e for k in kws)


def build_paths(
    df: pd.DataFrame,
    before: int = 5,
    after: int = 5,
    exclude_noise: list[str] | None = None,
    page_col: str = "page_name",
    event_col: str = "event_name",
    user_col: str = "user_id",
    session_col: str = "session_id",
    time_col: str = "event_time",
) -> pd.DataFrame:
    """构建提问前后路径序列。

    依赖 page_name 或 event_name。返回每个提问点的前后路径。
    """
    if df is None or df.empty:
        return pd.DataFrame()

    # 页面标识：page_name 或 event_name；会话表没有埋点时改走提问序列
    if page_col not in df.columns and event_col not in df.columns:
        return question_paths(df, before=before, after=after, user_col=user_col,
                              session_col=session_col, time_col=time_col)

    d = df.copy()
    if event_col in d.columns:
        d[event_col] = d[event_col].astype(str)
    if time_col in d.columns:
        d[time_col] = pd.to_datetime(d[time_col], errors="coerce")

    # 页面标识：优先 page_name，缺则用 event_name
    if page_col in d.columns:
        d["_node"] = d[page_col].astype(str).str.strip()
        d["_node"] = d["_node"].replace(["", "nan", "None", "null"], "")
        # 空页面回退 event_name
        d["_node"] = d["_node"].where(d["_node"] != "", d[event_col])
    else:
        d["_node"] = d[event_col]

    # 噪声过滤
    d["_noise"] = d[event_col].apply(lambda e: _is_noise(e, exclude_noise))
    d = d[~d["_noise"]]

    # 提问事件识别
    d["_is_question"] = d[event_col].str.lower().str.contains(
        "ask|提问|question|query|问", na=False
    )

    # 排序
    sort_cols = [user_col, session_col, time_col] if session_col in d.columns else [user_col, time_col]
    d = d.sort_values(sort_cols)

    records = []
    # 按（用户, 会话）或用户分组
    group_cols = [user_col] + ([session_col] if session_col in d.columns else [])
    for keys, grp in d.groupby(group_cols, dropna=False):
        grp = grp.reset_index(drop=True)
        nodes = grp["_node"].tolist()
        is_q = grp["_is_question"].tolist()
        for i, q in enumerate(is_q):
            if not q:
                continue
            lo = max(0, i - before)
            hi = min(len(nodes), i + after + 1)
            before_nodes = nodes[lo:i]
            after_nodes = nodes[i + 1:hi]
            records.append({
                "user_id": keys[0],
                "session_id": keys[1] if len(keys) > 1 else "",
                "question_node": nodes[i],
                "before_path": " -> ".join(before_nodes),
                "after_path": " -> ".join(after_nodes),
                "full_path": " -> ".join(nodes[lo:hi]),
            })

    if records:
        return pd.DataFrame(records)
    # 有 event_name 但匹配不到「提问」事件时，回退到问法序列
    return question_paths(df, before=before, after=after, user_col=user_col,
                          session_col=session_col, time_col=time_col)


def question_paths(
    df: pd.DataFrame,
    before: int = 5,
    after: int = 5,
    user_col: str = "user_id",
    session_col: str = "session_id",
    time_col: str = "event_time",
    text_col: str = "question_text",
) -> pd.DataFrame:
    """同一会话里的提问序列：节点用本地归并意图。"""
    if df is None or df.empty or text_col not in df.columns:
        return pd.DataFrame()
    from analysis import questions as q

    d = q.annotate_questions(df)
    d = d[d[text_col].map(q.is_valid_question)]
    if d.empty:
        return pd.DataFrame()
    if time_col in d.columns:
        d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
        d = d.sort_values([c for c in [user_col, session_col, time_col] if c in d.columns])
    d["_node"] = d["_std"]

    group_cols = [c for c in [user_col, session_col] if c in d.columns]
    if not group_cols:
        return pd.DataFrame()

    records = []
    for keys, grp in d.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        grp = grp.reset_index(drop=True)
        nodes = grp["_node"].astype(str).tolist()
        if len(nodes) < 2:
            # 单步会话也记一条，方便看孤立意图
            records.append({
                "user_id": keys[0] if keys else "",
                "session_id": keys[1] if len(keys) > 1 else "",
                "question_node": nodes[0] if nodes else "",
                "before_path": "",
                "after_path": "",
                "full_path": nodes[0] if nodes else "",
            })
            continue
        for i, node in enumerate(nodes):
            lo = max(0, i - before)
            hi = min(len(nodes), i + after + 1)
            records.append({
                "user_id": keys[0] if keys else "",
                "session_id": keys[1] if len(keys) > 1 else "",
                "question_node": node,
                "before_path": " -> ".join(nodes[lo:i]),
                "after_path": " -> ".join(nodes[i + 1:hi]),
                "full_path": " -> ".join(nodes[lo:hi]),
            })
    return pd.DataFrame(records)


def top_paths(
    paths_df: pd.DataFrame,
    top_n: int = 20,
) -> pd.DataFrame:
    """Top 路径：按（用户, 会话）去重后的路径序列频次降序。"""
    if paths_df is None or paths_df.empty:
        return pd.DataFrame()
    # 按 full_path 聚合，统计去重用户/会话数
    agg = paths_df.groupby("full_path").agg(
        频次=("full_path", "size"),
        用户数=("user_id", "nunique"),
        会话数=("session_id", "nunique"),
    ).reset_index()
    agg = agg.sort_values("频次", ascending=False).head(top_n).reset_index(drop=True)
    return agg


def path_before_top(
    paths_df: pd.DataFrame,
    top_n: int = 20,
) -> pd.DataFrame:
    """提问前来源 Top。"""
    if paths_df is None or paths_df.empty:
        return pd.DataFrame()
    c = Counter()
    for p in paths_df["before_path"]:
        for node in p.split(" -> "):
            if node.strip():
                c[node.strip()] += 1
    return pd.DataFrame(c.most_common(top_n), columns=["来源节点", "频次"])


def path_after_top(
    paths_df: pd.DataFrame,
    top_n: int = 20,
) -> pd.DataFrame:
    """提问后去向 Top。"""
    if paths_df is None or paths_df.empty:
        return pd.DataFrame()
    c = Counter()
    for p in paths_df["after_path"]:
        for node in p.split(" -> "):
            if node.strip():
                c[node.strip()] += 1
    return pd.DataFrame(c.most_common(top_n), columns=["去向节点", "频次"])
