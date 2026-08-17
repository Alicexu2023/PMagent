"""analysis/questions.py — 问法清洗、本地意图归并、高频问题、真实问法。

真实会话表没有 recognized_intent：先去掉零件预处理 JSON，再按业务规则归并到标准意图。
有意图字段时仍优先用已有标签（兼容旧测试与埋点数据）。
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pandas as pd

from core import config

PREPROCESS_SPLIT = re.compile(r"\[零件文件预处理上下文\]")
STATUS_JSON_TAIL = re.compile(r"""\{["']status["'].*$""", re.DOTALL | re.IGNORECASE)
MULTISPACE = re.compile(r"\s+")

# 更具体的规则靠前。报价类是主场景，但询盘/再算/工艺匹配优先单独切开。
INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("询盘推荐", ("推荐询盘", "帮我推荐", "帮我推", "适合我做", "询盘", "推荐一些", "推荐项目")),
    ("再次计算", ("再次计算", "重新计算", "再算一次", "重新算", "再算", "重算")),
    ("工艺匹配", ("匹配度", "拆解工艺", "能不能做", "能否做", "可不可以做",
                "有没有能力", "做不了", "能否加工", "工艺是否匹配", "生产工艺", "疑难点")),
    ("交期产能", ("交货期", "交期", "工期", "多久能好", "加工时间", "产能")),
    ("重量尺寸", ("单个重量", "重量多少", "多重", "多重少", "计算克重", "克重", "展开尺寸", "长宽厚")),
    ("成本报价", ("帮我报价", "报一下价", "报个价", "报下价", "给出报价", "报价", "估价",
                "核价", "多少钱", "单价", "价格", "多少元", "费用", "生产成本", "运费")),
    ("图纸解读", ("分析图纸", "解读图纸", "分析下图纸", "看一下图纸", "图纸分析", "看图纸")),
    ("材料确认", ("什么材质", "材料牌号", "材质是", "用什么材料")),
    ("数量确认", ("起订量", "数量多少")),
]

OTHER_INTENT = "其他/未归类"


def _as_str(s) -> str:
    return "" if pd.isna(s) else str(s).strip()


def clean_question_text(text) -> str:
    """去掉零件预处理上下文和尾部 JSON，只留用户原话。"""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    t = str(text).strip()
    if t.lower() in ("nan", "none", "null", "<na>"):
        return ""
    t = PREPROCESS_SPLIT.split(t, maxsplit=1)[0]
    t = re.split(r"预处理结果\s*[：:]", t, maxsplit=1)[0]
    t = STATUS_JSON_TAIL.sub("", t)
    t = MULTISPACE.sub(" ", t).strip()
    t = t.strip("，,;；。 \t\"'")
    return t


def is_valid_question(text: str) -> bool:
    """判断是否为有效提问（排除空、纯符号、明确测试）。"""
    t = clean_question_text(text)
    if not t:
        return False
    if t.lower() in config.TEST_WORDS:
        return False
    if t.isalnum() is False and not any(ch.isalnum() for ch in t):
        return False
    return True


def assign_intent(text: str) -> str:
    """按关键词把清洗后的问法归到标准意图。"""
    t = clean_question_text(text)
    if not t:
        return OTHER_INTENT
    for name, keys in INTENT_RULES:
        if any(k in t for k in keys):
            return name
    if ("重量" in t or "尺寸" in t) and "报价" not in t and "价格" not in t:
        return "重量尺寸"
    if "图纸" in t and "报价" not in t:
        return "图纸解读"
    if "材质" in t or "材料" in t:
        return "材料确认"
    if "推荐" in t:
        return "询盘推荐"
    return OTHER_INTENT


def _series_clean(d: pd.DataFrame, text_col: str) -> pd.Series:
    if text_col not in d.columns:
        return pd.Series("", index=d.index)
    return d[text_col].map(clean_question_text)


def _intent_labels(d: pd.DataFrame, intent_col: str) -> pd.Series:
    if intent_col not in d.columns:
        return pd.Series("", index=d.index)
    std = d[intent_col].astype(str).str.strip()
    return std.replace(["", "nan", "None", "null", "<NA>"], "")


def _has_intent_labels(d: pd.DataFrame, intent_col: str) -> bool:
    return bool((_intent_labels(d, intent_col) != "").any())


def standard_question_series(
    d: pd.DataFrame,
    intent_col: str = "recognized_intent",
    text_col: str = "question_text",
) -> pd.Series:
    """每行的标准问题：已有意图标签优先，否则本地归并。"""
    cleaned = _series_clean(d, text_col)
    labeled = _intent_labels(d, intent_col)
    if _has_intent_labels(d, intent_col):
        fallback = cleaned.where(cleaned != "", OTHER_INTENT)
        # 无标签时用清洗后的原话（测试数据里空意图对应空问题，会被有效性过滤）
        return labeled.where(labeled != "", fallback)
    return cleaned.map(assign_intent)


def annotate_questions(
    df: pd.DataFrame,
    intent_col: str = "recognized_intent",
    text_col: str = "question_text",
) -> pd.DataFrame:
    """给会话表加上 _q_clean / _std，供多处分析复用。"""
    if df is None or df.empty:
        return df
    d = df.copy()
    d["_q_clean"] = _series_clean(d, text_col)
    d["_std"] = standard_question_series(d, intent_col, text_col)
    return d


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

    d = annotate_questions(df, intent_col, text_col)
    if text_col in d.columns:
        d = d[d[text_col].map(is_valid_question)]
    else:
        d = d[d["_std"].map(is_valid_question)]

    if d.empty:
        return pd.DataFrame()

    agg_kw: dict[str, Any] = {
        "提问次数": ("_std", "size"),
        "提问人数": (user_col, "nunique") if user_col in d.columns else ("_std", "size"),
    }
    if time_col in d.columns:
        agg_kw["最近时间"] = (time_col, "max")
    agg = d.groupby("_std", dropna=False).agg(**agg_kw).reset_index()
    agg = agg.rename(columns={"_std": "标准问题"})
    total = int(agg["提问次数"].sum())
    agg["占比"] = (agg["提问次数"] / total * 100).round(2)
    agg = agg.sort_values("提问次数", ascending=False).reset_index(drop=True)
    return agg


def exact_questions(
    df: pd.DataFrame,
    text_col: str = "question_text",
    user_col: str = "user_id",
    top_n: int = 20,
) -> pd.DataFrame:
    """清洗后的高频原话（给同义表达/运营看原句，不把预处理 JSON 当问题）。"""
    if df is None or df.empty or text_col not in df.columns:
        return pd.DataFrame()
    d = df.copy()
    d["_q_clean"] = _series_clean(d, text_col)
    d = d[d["_q_clean"].map(is_valid_question)]
    if d.empty:
        return pd.DataFrame()
    agg_kw: dict[str, Any] = {"提问次数": ("_q_clean", "size")}
    if user_col in d.columns:
        agg_kw["提问人数"] = (user_col, "nunique")
    agg = d.groupby("_q_clean").agg(**agg_kw).reset_index().rename(columns={"_q_clean": "问法"})
    total = int(agg["提问次数"].sum())
    agg["占比"] = (agg["提问次数"] / total * 100).round(2)
    return agg.sort_values("提问次数", ascending=False).head(top_n).reset_index(drop=True)


def _diversity_sample(texts: list[str], freqs: dict[str, int], top_n: int = 20) -> list[str]:
    """按频次 + 表达多样性抽取 top_n 条真实问法。"""
    ordered = sorted(set(texts), key=lambda t: (-freqs.get(t, 0), len(t)))
    picked: list[str] = []
    seen_norm: set[str] = set()

    def _norm(t: str) -> str:
        return re.sub(r"[\W_]+", "", t).lower()

    for t in ordered:
        if len(picked) >= top_n:
            break
        n = _norm(t)
        if n in seen_norm:
            continue
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
    """提取某个标准问题下的真实问法（前 top_n 条，兼顾频次与多样性）。"""
    if df is None or df.empty:
        return []

    d = annotate_questions(df, intent_col, text_col)
    sub = d[d["_std"] == std_question].copy()
    if sub.empty:
        return []

    sub["_txt"] = sub["_q_clean"].where(sub["_q_clean"] != "", sub[text_col].astype(str).str.strip() if text_col in sub.columns else "")
    sub = sub[sub["_txt"] != ""]
    if sub.empty:
        return []

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
            "标准问题": std_question,
            "置信度": _as_str(row.get("intent_confidence", "")) if "intent_confidence" in sub.columns else "",
            "回答状态": _as_str(row.get("answer_status", "")) if "answer_status" in sub.columns else "",
        }
        out.append(item)
    return out


def question_trend(
    df: pd.DataFrame,
    std_question: str,
    freq: str = "D",
    intent_col: str = "recognized_intent",
    text_col: str = "question_text",
    time_col: str = "event_time",
) -> pd.DataFrame:
    """某标准问题的时间趋势。"""
    if df is None or df.empty:
        return pd.DataFrame()
    d = annotate_questions(df, intent_col, text_col)
    sub = d[d["_std"] == std_question].copy()
    if sub.empty or time_col not in sub.columns:
        return pd.DataFrame()
    sub[time_col] = pd.to_datetime(sub[time_col], errors="coerce")
    sub = sub.dropna(subset=[time_col])
    if sub.empty:
        return pd.DataFrame()
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
    """会话内/时间窗内重复提问统计。比较清洗后的问法，避免预处理 JSON 把同一句拆开。"""
    if df is None or df.empty:
        return 0, 0, pd.DataFrame()

    window = window_min if window_min is not None else config.REPEAT_ASK_WINDOW_MIN
    d = df.copy()
    if time_col not in d.columns or user_col not in d.columns:
        return 0, 0, pd.DataFrame()
    d[time_col] = pd.to_datetime(d[time_col], errors="coerce")
    d = d.dropna(subset=[time_col, user_col])
    d = d.sort_values([user_col, time_col])

    d["_txt"] = _series_clean(d, text_col) if text_col in d.columns else pd.Series("", index=d.index)
    d = d[d["_txt"].map(is_valid_question)]

    valid_total = len(d)
    if valid_total == 0:
        return 0, 0, pd.DataFrame()

    repeat_count = 0
    repeat_rows = []
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
