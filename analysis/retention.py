"""analysis/retention.py — 留存分析。

默认以首次提问为起点，计算次日/7日/30日留存。
支持新老用户、首次问题类型对比。
样本 < 30 人标注"样本不足"。
"""
from __future__ import annotations

import pandas as pd

from core import config


def _first_active(df: pd.DataFrame, user_col: str, time_col: str) -> pd.Series:
    """每个用户的首次提问时间。"""
    d = df[[user_col, time_col]].copy()
    d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
    d = d.dropna(subset=[time_col])
    return d.groupby(user_col)[time_col].min()


def retention_analysis(
    df: pd.DataFrame,
    periods: list[int] | None = None,
    user_col: str = "user_id",
    time_col: str = "event_time",
    text_col: str = "question_text",
) -> tuple[pd.DataFrame, str]:
    """计算 N 日留存率。

    返回 (留存 DataFrame: 周期/留存人数/留存率(%)/样本量, 提示信息)。
    """
    if df is None or df.empty:
        return pd.DataFrame(), "无数据"

    periods = periods or config.RETENTION_PERIODS
    if user_col not in df.columns or time_col not in df.columns:
        return pd.DataFrame(), "缺少 user_id 或 event_time，无法计算留存"

    d = df.copy()
    d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
    d = d.dropna(subset=[time_col, user_col])

    # 只统计"发起提问"事件（有 question_text 或有 text_col）
    if text_col in d.columns:
        d = d[d[text_col].astype(str).str.strip() != ""]

    if d.empty:
        return pd.DataFrame(), "无有效提问数据"

    first = d.groupby(user_col)[time_col].min()
    cohort_size = len(first)

    # 数据时间跨度检测：不足 N+1 天时，D(N) 留存数据不足
    time_span_days = (d[time_col].max() - d[time_col].min()).days if len(d) > 1 else 0

    rows = []
    for n in periods:
        retained = 0
        for uid, t0 in first.items():
            target_day = t0 + pd.Timedelta(days=n)
            # 首次提问后第 N 日当天再次提问（含当天之后）
            later = d[(d[user_col] == uid) & (d[time_col] >= target_day)]
            if not later.empty:
                retained += 1
        rate = (retained / cohort_size * 100) if cohort_size else 0.0
        # 数据跨度不足以观察 N 日留存时，标注数据不足
        insufficient = time_span_days < n
        rows.append({
            "周期": f"D{n}",
            "留存人数": retained,
            "留存率(%)": round(rate, 2) if not insufficient else None,
            "样本量": cohort_size,
            "数据状态": "数据不足" if insufficient else "正常",
        })

    note = ""
    if cohort_size < config.RETENTION_SAMPLE_MIN:
        note = f"样本不足（{cohort_size} 人 < {config.RETENTION_SAMPLE_MIN}），结果仅供参考，不作强判断"
    if time_span_days < 7:
        note = (note + "；" if note else "") + "当前为单周数据，D7/D30 留存需至少两周数据"

    return pd.DataFrame(rows), note


def retention_by_group(
    df: pd.DataFrame,
    group_col: str,
    periods: list[int] | None = None,
    user_col: str = "user_id",
    time_col: str = "event_time",
) -> dict[str, pd.DataFrame]:
    """按某维度（新老用户 / 首次问题类型）分组计算留存。"""
    if df is None or df.empty or group_col not in df.columns:
        return {}
    result = {}
    for val, grp in df.groupby(group_col):
        df_r, _ = retention_analysis(grp, periods, user_col, time_col)
        if not df_r.empty:
            result[str(val)] = df_r
    return result


# ---------------------------------------------------------------------------
# 多周分析：工厂周留存 + 环比
# ---------------------------------------------------------------------------
def weekly_retention(
    prev_df: pd.DataFrame,
    curr_df: pd.DataFrame,
    id_col: str = "factory_id",
) -> dict:
    """工厂周留存：上一周活跃工厂中，本周仍活跃的比例。

    返回 {上周活跃数, 本周活跃数, 留存数, 流失数, 新增数, 周留存率(%)}。
    """
    if prev_df is None or prev_df.empty or curr_df is None or curr_df.empty:
        return {}
    id_col_prev = id_col if id_col in prev_df.columns else "user_id"
    id_col_curr = id_col if id_col in curr_df.columns else "user_id"
    if id_col_prev not in prev_df.columns or id_col_curr not in curr_df.columns:
        return {}

    prev_set = set(prev_df[id_col_prev].astype(str).str.strip())
    curr_set = set(curr_df[id_col_curr].astype(str).str.strip())
    prev_set.discard("")
    curr_set.discard("")
    prev_set.discard("nan")
    curr_set.discard("nan")

    retained = prev_set & curr_set
    lost = prev_set - curr_set
    new = curr_set - prev_set

    return {
        "上周活跃数": len(prev_set),
        "本周活跃数": len(curr_set),
        "留存数": len(retained),
        "流失数": len(lost),
        "新增数": len(new),
        "周留存率(%)": round(len(retained) / len(prev_set) * 100, 2) if prev_set else 0.0,
    }


def week_over_week(
    prev_df: pd.DataFrame,
    curr_df: pd.DataFrame,
    metric_cols: list[str] | None = None,
    id_col: str = "factory_id",
) -> pd.DataFrame:
    """环比：本周 vs 上周的指标对比（按数值列求和 + 人均）。

    返回 DataFrame：指标 / 上周 / 本周 / 差值 / 变化率(%)。
    """
    default_metrics = ["usage_days", "session_count", "question_count", "upload_count"]
    metric_cols = metric_cols or default_metrics
    if prev_df is None or prev_df.empty or curr_df is None or curr_df.empty:
        return pd.DataFrame()

    metric_map = {
        "usage_days": "使用天数",
        "session_count": "会话次数",
        "question_count": "提问数",
        "upload_count": "上传图纸数",
    }

    rows = []
    for mc in metric_cols:
        if mc not in prev_df.columns or mc not in curr_df.columns:
            continue
        prev_sum = pd.to_numeric(prev_df[mc], errors="coerce").fillna(0).sum()
        curr_sum = pd.to_numeric(curr_df[mc], errors="coerce").fillna(0).sum()
        diff = curr_sum - prev_sum
        rate = round((curr_sum - prev_sum) / prev_sum * 100, 2) if prev_sum else None
        rows.append({
            "指标": metric_map.get(mc, mc),
            "上周": float(prev_sum),
            "本周": float(curr_sum),
            "差值": float(diff),
            "变化率(%)": rate,
        })

    # 活跃工厂数（单独一行）
    if id_col in prev_df.columns and id_col in curr_df.columns:
        prev_cnt = prev_df[id_col].nunique()
        curr_cnt = curr_df[id_col].nunique()
        rows.append({
            "指标": "活跃工厂数",
            "上周": float(prev_cnt),
            "本周": float(curr_cnt),
            "差值": float(curr_cnt - prev_cnt),
            "变化率(%)": round((curr_cnt - prev_cnt) / prev_cnt * 100, 2) if prev_cnt else None,
        })

    return pd.DataFrame(rows)
