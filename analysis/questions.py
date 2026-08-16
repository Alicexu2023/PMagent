"""analysis/questions.py — 高频问题、真实问法抽取、AI 归并、同义表达。

- 高频标准问题：提问次数、人数、占比、时间趋势
- 每个问题前 20 条真实问法（按频次 + 表达多样性抽取）
- AI 归并：真实问法 -> 标准问题（可人工修改）
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from core import config


def _as_str(s) -> str:
    return "" if pd.isna(s) else str(s).strip()


def is_valid_question(text: str) -> bool:
    """判断是否为有效提问（排除空、纯符号、明确测试）。"""
    t = _as_str(text)
    if not t:
        return False
    if t.lower() in config.TEST_WORDS:
        return False
    if t.isalnum() is False and not any(ch.isalnum() for ch in t):
        # 纯符号
        return False
    return True


def high_freq_questions(
    df: pd.DataFrame,
    intent_col: str = "recognized_intent",
    text_col: str = "question_text",
    user_col: str = "user_id",
    time_col: str = "event_time",
) -> pd.DataFrame:
    """统计高频标准问题。

    返回列：标准问题、提问次数、提问人数、占比、最近时间
    """
    if df is None or df.empty:
        return pd.DataFrame()

    d = df.copy()
    # 标准问题优先取 recognized_intent，空则回退 question_text
    std = d[intent_col].astype(str).str.strip() if intent_col in d.columns else None
    if std is None:
        std = pd.Series("", index=d.index)
    else:
        std = std.replace(["", "nan", "None", "null"], "")
    txt = d[text_col].astype(str).str.strip() if text_col in d.columns else pd.Series("", index=d.index)

    # 标准问题为空时用文本填充
    final_std = std.where(std != "", txt)
    d["_std"] = final_std

    # 过滤有效提问
    d = d[d["_std"].apply(is_valid_question)]

    if d.empty:
        return pd.DataFrame()

    agg = d.groupby("_std").agg(
        提问次数=("_std", "size"),
        提问人数=(user_col, "nunique"),
        最近时间=(time_col, "max") if time_col in d.columns else ("_std", lambda _: ""),
    ).reset_index()
    agg = agg.rename(columns={"_std": "标准问题"})
    total = int(agg["提问次数"].sum())
    agg["占比"] = (agg["提问次数"] / total * 100).round(2)
    agg = agg.sort_values("提问次数", ascending=False).reset_index(drop=True)
    return agg


def _diversity_sample(texts: list[str], freqs: dict[str, int], top_n: int = 20) -> list[str]:
    """按频次 + 表达多样性抽取 top_n 条真实问法。

    简单策略：优先高频，同时避免高度相似（前缀相同/归一化后相同）的句子刷屏。
    """
    # 按频次降序
    ordered = sorted(set(texts), key=lambda t: (-freqs.get(t, 0), len(t)))
    picked: list[str] = []
    seen_norm: set[str] = set()

    def _norm(t: str) -> str:
        # 归一化：去标点、空格、转小写
        import re
        return re.sub(r"[\W_]+", "", t).lower()

    for t in ordered:
        if len(picked) >= top_n:
            break
        n = _norm(t)
        # 完全相同的归一化结果只保留一次；前缀重复太严重的也跳过一部分
        if n in seen_norm:
            continue
        # 表达多样性：若已有很多条，跳过与已有条目前缀相同的
        if len(picked) >= 5:
            prefix_dup = any(_norm(p)[:6] == n[:6] and len(n[:6]) >= 4 for p in picked)
            if prefix_dup and len(picked) >= 10:
                continue
        picked.append(t)
        seen_norm.add(n)

    return picked


def real_questions(
    df: pd.DataFrame,
    std_question: str,
    intent_col: str = "recognized_intent",
    text_col: str = "question_text",
    user_col: str = "user_id",
    top_n: int = 20,
) -> list[dict[str, Any]]:
    """提取某个标准问题下的真实问法（前 top_n 条，兼顾频次与多样性）。

    每条含：问法、次数、人数、识别意图、置信度、回答状态。
    """
    if df is None or df.empty:
        return []

    d = df.copy()
    std = d[intent_col].astype(str).str.strip() if intent_col in d.columns else pd.Series("", index=d.index)
    std = std.replace(["", "nan", "None", "null"], "")
    txt = d[text_col].astype(str).str.strip() if text_col in d.columns else pd.Series("", index=d.index)
    final_std = std.where(std != "", txt)

    mask = final_std == std_question
    sub = d[mask].copy()
    if sub.empty:
        return []

    sub["_txt"] = sub[text_col].astype(str).str.strip()
    sub = sub[sub["_txt"] != ""]

    freqs: dict[str, int] = sub["_txt"].value_counts().to_dict()
    picked_texts = _diversity_sample(list(sub["_txt"]), freqs, top_n)

    out = []
    for t in picked_texts:
        row = sub[sub["_txt"] == t].iloc[0]
        item = {
            "问法": t,
            "次数": freqs.get(t, 0),
            "人数": int(sub[sub["_txt"] == t][user_col].nunique()) if user_col in sub.columns else 0,
            "识别意图": _as_str(row.get(intent_col, "")) if intent_col in sub.columns else "",
            "置信度": _as_str(row.get("intent_confidence", "")) if "intent_confidence" in sub.columns else "",
            "回答状态": _as_str(row.get("answer_status", "")) if "answer_status" in sub.columns else "",
        }
        out.append(item)
    return out


def question_trend(
    df: pd.DataFrame,
    std_question: str,
    freq: str = "D",  # D=日, W=周
    intent_col: str = "recognized_intent",
    text_col: str = "question_text",
    time_col: str = "event_time",
) -> pd.DataFrame:
    """某标准问题的时间趋势。"""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    std = d[intent_col].astype(str).str.strip() if intent_col in d.columns else pd.Series("", index=d.index)
    std = std.replace(["", "nan", "None", "null"], "")
    txt = d[text_col].astype(str).str.strip() if text_col in d.columns else pd.Series("", index=d.index)
    final_std = std.where(std != "", txt)
    sub = d[final_std == std_question].copy()
    if sub.empty or time_col not in sub.columns:
        return pd.DataFrame()
    sub[time_col] = pd.to_datetime(sub[time_col], errors="coerce")
    sub = sub.dropna(subset=[time_col])
    sub["_t"] = sub[time_col].dt.to_period(freq).astype(str)
    trend = sub.groupby("_t").size().reset_index(name="提问次数")
    trend = trend.rename(columns={"_t": "时间"})
    return trend


def repeat_questions(
    df: pd.DataFrame,
    window_min: int | None = None,
    user_col: str = "user_id",
    time_col: str = "event_time",
    text_col: str = "question_text",
    session_col: str = "session_id",
) -> tuple[int, int, pd.DataFrame]:
    """会话内/时间窗内重复提问统计。

    返回 (重复提问数, 有效提问数, 重复明细 DataFrame)。
    """
    if df is None or df.empty:
        return 0, 0, pd.DataFrame()

    window = window_min if window_min is not None else config.REPEAT_ASK_WINDOW_MIN
    d = df.copy()
    if time_col not in d.columns or user_col not in d.columns:
        return 0, 0, pd.DataFrame()
    d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
    d = d.dropna(subset=[time_col, user_col])
    d = d.sort_values([user_col, time_col])

    txt = d[text_col].astype(str).str.strip() if text_col in d.columns else pd.Series("", index=d.index)
    d["_txt"] = txt
    # 排除空问题（NaN 用 notna 判断，pandas 3.0 astype(str) 后 == 比较失效）
    d["_valid"] = d[text_col].notna() & (d["_txt"] != "") & (d["_txt"] != "nan") & (d["_txt"] != "<NA>")
    d = d[d["_valid"]]

    valid_total = len(d)
    if valid_total == 0:
        return 0, 0, pd.DataFrame()

    repeat_count = 0
    repeat_rows = []
    # 按用户分组，检测时间窗内是否再次问相同文本
    for uid, grp in d.groupby(user_col):
        grp = grp.sort_values(time_col)
        seen: dict[str, pd.Timestamp] = {}
        for _, row in grp.iterrows():
            t = row["_txt"]
            cur_t = row[time_col]
            if t in seen:
                if (cur_t - seen[t]).total_seconds() <= window * 60:
                    repeat_count += 1
                    repeat_rows.append(row)
            seen[t] = cur_t

    return repeat_count, valid_total, pd.DataFrame(repeat_rows) if repeat_rows else pd.DataFrame()
