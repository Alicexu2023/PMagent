"""analysis/adoption.py — 功能采用分析。

指标：功能使用人数、使用次数、使用会话数、渗透率、人均使用频次、使用天数。
支持按功能上线时间对比上线前后。
"""
from __future__ import annotations

import pandas as pd

from analysis.product import is_real_upload, upload_mask


def upload_type_adoption(
    df: pd.DataFrame,
    user_col: str = "user_id",
    session_col: str = "session_id",
    time_col: str = "event_time",
) -> pd.DataFrame:
    """把上传文件类型当作功能点：无 feature_name 时的采用分析。"""
    if df is None or df.empty or "upload_file_type" not in df.columns:
        return pd.DataFrame()
    d = df.loc[upload_mask(df)].copy()
    if d.empty:
        return pd.DataFrame()
    d["_feat"] = d["upload_file_type"].astype(str).str.strip().str.lower()
    rows = []
    exploded = d.assign(_feat=d["_feat"].str.split(",")).explode("_feat")
    exploded["_feat"] = exploded["_feat"].astype(str).str.strip()
    exploded = exploded[exploded["_feat"].map(is_real_upload)]
    total_users = int(df[user_col].nunique()) if user_col in df.columns else 0
    if time_col in exploded.columns:
        exploded[time_col] = pd.to_datetime(exploded[time_col], errors="coerce")
        exploded["_day"] = exploded[time_col].dt.date
    else:
        exploded["_day"] = None
    for feat, grp in exploded.groupby("_feat"):
        users = grp[user_col].nunique() if user_col in grp.columns else 0
        events = len(grp)
        sessions = grp[session_col].nunique() if session_col in grp.columns else 0
        days = grp["_day"].nunique() if grp["_day"].notna().any() else 0
        rows.append({
            "功能": feat,
            "使用人数": int(users),
            "使用次数": int(events),
            "使用会话数": int(sessions),
            "人均频次": round(events / users, 2) if users else 0.0,
            "使用天数": int(days),
            "渗透率(%)": round(users / total_users * 100, 2) if total_users else 0.0,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("使用人数", ascending=False).reset_index(drop=True)
    return out


def adoption_analysis(
    df: pd.DataFrame,
    feature_col: str = "feature_name",
    user_col: str = "user_id",
    session_col: str = "session_id",
    time_col: str = "event_time",
    eligible_total: int | None = None,
) -> pd.DataFrame:
    """计算各功能的采用指标。

    返回列：功能、使用人数、使用次数、使用会话数、人均频次、使用天数、渗透率(%)。
    eligible_total：符合条件用户总数（用于渗透率）；缺省用全体 user_id 去重数。
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if feature_col not in df.columns:
        return upload_type_adoption(df, user_col=user_col, session_col=session_col, time_col=time_col)

    d = df.copy()
    d[feature_col] = d[feature_col].astype(str).str.strip()
    d = d[d[feature_col].isin(["", "nan", "None", "null"]) == False]  # noqa: E712

    if d.empty:
        return pd.DataFrame()

    if time_col in d.columns:
        d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
        d["_day"] = d[time_col].dt.date
    else:
        d["_day"] = None

    total_users = eligible_total if eligible_total is not None else (
        int(df[user_col].nunique()) if user_col in df.columns else 0
    )

    rows = []
    for feat, grp in d.groupby(feature_col):
        users = grp[user_col].nunique() if user_col in grp.columns else 0
        events = len(grp)
        sessions = grp[session_col].nunique() if session_col in grp.columns else 0
        days = grp["_day"].nunique() if "_day" in grp.columns and grp["_day"].notna().any() else 0
        freq_per_user = round(events / users, 2) if users else 0.0
        days_per_user = round(days / users, 2) if users else 0.0
        penetration = round(users / total_users * 100, 2) if total_users else 0.0
        rows.append({
            "功能": feat,
            "使用人数": int(users),
            "使用次数": int(events),
            "使用会话数": int(sessions),
            "人均频次": freq_per_user,
            "使用天数": int(days),
            "渗透率(%)": penetration,
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("使用人数", ascending=False).reset_index(drop=True)
    return out


def adoption_before_after(
    df: pd.DataFrame,
    feature: str,
    launch_date: str,
    feature_col: str = "feature_name",
    user_col: str = "user_id",
    time_col: str = "event_time",
) -> tuple[pd.DataFrame, str]:
    """功能上线前后对比。

    返回 (对比 DataFrame, 提示信息)。
    """
    if df is None or df.empty or feature_col not in df.columns or time_col not in df.columns:
        return pd.DataFrame(), "缺少 feature_name 或 event_time，无法对比上线前后"

    d = df.copy()
    d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
    d = d.dropna(subset=[time_col])
    launch = pd.to_datetime(launch_date)

    sub = d[d[feature_col].astype(str).str.strip() == feature]
    if sub.empty:
        return pd.DataFrame(), f"未找到功能「{feature}」的使用事件"

    before = sub[sub[time_col] < launch]
    after = sub[sub[time_col] >= launch]

    def _metrics(part: pd.DataFrame) -> dict:
        users = part[user_col].nunique() if user_col in part.columns else 0
        events = len(part)
        freq = round(events / users, 2) if users else 0.0
        return {"使用人数": int(users), "使用次数": int(events), "人均频次": freq}

    b = _metrics(before)
    a = _metrics(after)

    rows = []
    for metric in ["使用人数", "使用次数", "人均频次"]:
        bv, av = b[metric], a[metric]
        diff = av - bv
        rate = round((av - bv) / bv * 100, 2) if bv else None
        rows.append({
            "指标": metric,
            "上线前": bv,
            "上线后": av,
            "差值": diff,
            "变化率(%)": rate,
        })

    note = ""
    if before.empty or after.empty:
        note = "上线前或上线后样本为空，对比结果仅供参考"

    return pd.DataFrame(rows), note
