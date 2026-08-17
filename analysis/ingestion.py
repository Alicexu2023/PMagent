"""analysis/ingestion.py — 数据读取、字段映射、质量门禁。

三表上传：用户总表 CSV、会话表 CSV、反馈 XLSX。
- UTF-8-SIG / GBK 自动识别
- 周次识别
- 字段固定映射
- 文件哈希去重
- 全空列清理
- 空问题 / 超长文本处理
- 质量报告：原始/有效/排除数及原因、可做/不可做分析
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from core import config
from core import storage


# ---------------------------------------------------------------------------
# 字段映射：用户提供的列名 -> 规范字段名
# ---------------------------------------------------------------------------
# 三张表各有固定列名，这里做别名归一（大小写、空格、中英文对照）。
# 本场景为 B2B 供应链：会话表无 user_id，用"工厂ID"作为用户维度代理。
FIELD_ALIASES = {
    "user_id": ["user_id", "userid", "用户ID", "用户id", "工号", "用户编号", "uid",
                "工厂ID", "工厂id", "工厂编号", "工厂标识"],
    "factory_id": ["factory_id", "工厂ID", "工厂id", "工厂编号", "factoryid"],
    "company_name": ["company_name", "公司名称", "公司", "企业名称", "公司名"],
    "event_time": ["event_time", "time", "时间", "发生时间", "事件时间", "提问时间",
                   "提问日期", "datetime", "日期"],
    "week_label": ["week_label", "统计周期", "周期", "周次", "周区间"],
    "event_name": ["event_name", "event", "事件", "事件名", "事件名称", "行为", "动作"],
    "question_id": ["question_id", "qid", "问题ID", "问题id", "提问ID"],
    "question_text": ["question_text", "question", "问题", "问题文本", "提问", "提问内容",
                      "问法", "用户问题", "用户问题原文", "问题原文", "用户提问内容"],
    "session_id": ["session_id", "会话ID", "会话id", "会话", "session", "会话编号"],
    "recognized_intent": ["recognized_intent", "intent", "意图", "识别意图", "识别结果", "标准问题", "标准问法"],
    "intent_confidence": ["intent_confidence", "confidence", "置信度", "置信分数", "score"],
    "answer_status": ["answer_status", "status", "回答状态", "回答结果", "状态"],
    "answer_text": ["answer_text", "智能体回答", "回答内容", "回答", "智能体回答内容", "回复"],
    "business_result": ["business_result", "result", "业务结果", "业务动作", "转化", "完成"],
    "page_name": ["page_name", "page", "页面", "页面名称", "模块", "page_id"],
    "feature_name": ["feature_name", "feature", "功能", "功能名称", "功能入口", "功能点"],
    "event_detail": ["event_detail", "detail", "详情", "事件详情", "附加信息", "按钮"],
    "user_properties": ["user_properties", "properties", "属性", "用户属性", "岗位"],
    "upload_file_type": ["upload_file_type", "上传文件类型", "文件类型", "上传图纸类型", "上传类型"],
    "upload_count": ["upload_count", "本周上传图纸数", "上传图纸数", "上传数"],
    "process_type": ["process_type", "工艺类型", "主营工艺", "工艺"],
    # 用户总表特有（周报汇总维度）
    "role": ["role", "角色", "使用人角色", "主要使用角色"],
    "scene": ["scene", "场景", "本周主要使用场景", "主要使用场景", "使用场景"],
    "member_type": ["member_type", "会员类型", "会员", "会员等级", "会员分层"],
    "level": ["level", "当前主分层", "主分层", "分层", "会员分层", "等级"],
    "region": ["region", "区域", "地区", "所在地区"],
    "usage_days": ["usage_days", "本周使用天数", "使用天数"],
    "session_count": ["session_count", "本周会话次数", "会话次数"],
    "question_count": ["question_count", "本周用户提问数", "用户提问数", "提问数"],
    "is_new": ["is_new", "本周是否新增使用", "是否新增"],
    "is_return": ["is_return", "本周是否回流", "是否回流"],
    "has_new_demand": ["has_new_demand", "本周是否提出新需求", "是否提出新需求"],
    "new_demand_summary": ["new_demand_summary", "新需求摘要"],
    "has_issue": ["has_issue", "本周是否出现问题", "是否出现问题"],
    "issue_summary": ["issue_summary", "问题摘要"],
    "value_tag": ["value_tag", "特殊价值标签"],
    "level_reason": ["level_reason", "分层原因"],
    "next_action": ["next_action", "下一步动作"],
}

# 反向：规范名 -> 别名列表
_ALIAS_TO_FIELD: dict[str, str] = {}
for _field, _aliases in FIELD_ALIASES.items():
    for _a in _aliases:
        _ALIAS_TO_FIELD[_a.lower().strip()] = _field


def normalize_column(col: str) -> str:
    """把原始列名归一化为规范字段名；无法识别返回原列名（去空格）。"""
    key = str(col).strip().lower()
    return _ALIAS_TO_FIELD.get(key, str(col).strip())


@dataclass
class QualityReport:
    """质量门禁报告。"""
    table_type: str = ""          # users / sessions / feedback
    file_name: str = ""
    raw_count: int = 0
    valid_count: int = 0
    excluded_count: int = 0
    exclude_reasons: dict[str, int] = field(default_factory=dict)  # 原因 -> 数量
    missing_required: list[str] = field(default_factory=list)      # 缺失的必需字段
    available_analyses: list[str] = field(default_factory=list)     # 可做分析
    unavailable_analyses: dict[str, list[str]] = field(default_factory=dict)  # 不可做分析 -> 缺字段
    week_label: str = ""
    extra_info: dict[str, Any] = field(default_factory=dict)        # 关联差异等

    def to_dict(self) -> dict:
        return {
            "table_type": self.table_type,
            "file_name": self.file_name,
            "raw_count": self.raw_count,
            "valid_count": self.valid_count,
            "excluded_count": self.excluded_count,
            "exclude_reasons": self.exclude_reasons,
            "missing_required": self.missing_required,
            "available_analyses": self.available_analyses,
            "unavailable_analyses": self.unavailable_analyses,
            "week_label": self.week_label,
            "extra_info": self.extra_info,
        }


def file_hash(path: Path) -> str:
    """文件 SHA256 哈希，用于去重。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_week_label(df: pd.DataFrame, time_col: str = "event_time") -> str:
    """从时间列识别周次（ISO 周，如 2026-W33）。

    优先识别 week_label 字段（如"2026-07-20 至 2026-07-26"周区间文本），
    其次从 event_time 解析。
    """
    # 1) 已有 week_label 字段（周区间文本）
    if "week_label" in df.columns:
        vals = df["week_label"].dropna().astype(str).unique()
        if len(vals) > 0:
            v = vals[0]
            m = re.search(r"(\d{4})-(\d{2})-(\d{2})", v)
            if m:
                try:
                    d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    iso = d.isocalendar()
                    return f"{iso.year}-W{iso.week:02d}"
                except ValueError:
                    pass
            return v

    # 2) 从 event_time 解析
    if time_col not in df.columns:
        return ""
    try:
        ts = pd.to_datetime(df[time_col], errors="coerce")
        ts = ts.dropna()
        if ts.empty:
            return ""
        latest = ts.max()
        iso = latest.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    except Exception:
        return ""


def _read_csv(path: Path) -> pd.DataFrame:
    """读取 CSV，自动识别 UTF-8-SIG / GBK。"""
    # 先试 UTF-8-SIG
    for enc in ["utf-8-sig", "utf-8", "gbk", "gb18030"]:
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except (UnicodeDecodeError, UnicodeError):
            continue
    # 兜底
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, errors="replace")


def _read_xlsx(path: Path) -> pd.DataFrame:
    return pd.read_excel(path, dtype=str)


def load_file(path: str | Path) -> pd.DataFrame:
    """按扩展名读取 CSV/XLSX。"""
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return _read_csv(p)
    return _read_xlsx(p)


def clean_empty_columns(df: pd.DataFrame) -> pd.DataFrame:
    """清理全空列（含 Unnamed 列）。"""
    # 去掉列名含 Unnamed 且内容全空的列
    drop_cols = []
    for col in df.columns:
        if str(col).startswith("Unnamed") and df[col].isna().all():
            drop_cols.append(col)
    if drop_cols:
        df = df.drop(columns=drop_cols)
    return df


def map_fields(df: pd.DataFrame) -> pd.DataFrame:
    """字段固定映射：原始列名 -> 规范字段名。"""
    rename = {}
    for col in df.columns:
        norm = normalize_column(col)
        if norm != str(col).strip():
            rename[col] = norm
    if rename:
        df = df.rename(columns=rename)
    return df


def normalize_user_dimension(df: pd.DataFrame) -> pd.DataFrame:
    """用户维度归一化：无 user_id 但有 factory_id 时，用工厂ID作为用户维度代理。

    B2B 供应链场景：会话表/用户总表以"工厂"为单位，无传统 user_id。
    """
    if df is None or df.empty:
        return df
    if "user_id" not in df.columns and "factory_id" in df.columns:
        df = df.copy()
        df["user_id"] = df["factory_id"]
    return df


def quality_check(
    df: pd.DataFrame,
    table_type: str,
    file_name: str = "",
    week_label: str = "",
) -> QualityReport:
    """对单张表执行质量门禁。

    必需字段按表类型区分（以开发.txt + 真实样表为准）：
    - sessions：工厂ID(user_id) + 提问时间(event_time)
    - users：工厂ID(user_id)（周报汇总表，无时间列）
    - feedback：可空，不阻塞
    """
    rep = QualityReport(table_type=table_type, file_name=file_name)
    rep.raw_count = len(df)
    rep.week_label = week_label or detect_week_label(df)

    # 全空列清理 + 字段映射 + 用户维度归一化
    df = clean_empty_columns(df)
    df = map_fields(df)
    df = normalize_user_dimension(df)

    # 必需字段检查（按表类型）
    if table_type == "sessions":
        required = ["user_id", "event_time"]
    elif table_type == "users":
        required = ["user_id"]
    else:
        required = []
    for f in required:
        if f not in df.columns:
            rep.missing_required.append(f)

    # 反馈表（feedback）可能无 user_id 等，放宽：只要有内容即有效
    if table_type == "feedback":
        # 反馈表为空不阻塞
        rep.valid_count = len(df)
        rep.excluded_count = 0
        rep.exclude_reasons = {}
        if df.empty:
            rep.extra_info["note"] = "反馈表为空，不阻塞分析"
        rep.available_analyses = ["满意度反馈（若有数据）"]
        rep.unavailable_analyses = {}
        return rep

    # 若缺失必需字段，直接阻断：无法分析
    if rep.missing_required:
        rep.valid_count = 0
        rep.excluded_count = len(df)
        rep.exclude_reasons["缺少必需字段: " + ", ".join(rep.missing_required)] = len(df)
        rep.available_analyses = []
        rep.unavailable_analyses = {"全部分析": rep.missing_required}
        return rep

    # 开始逐行质检，记录排除原因
    valid_mask = pd.Series(True, index=df.index)
    reasons: dict[str, int] = {}

    def _mark(mask, reason: str):
        nonlocal valid_mask
        cnt = int((mask & valid_mask).sum())
        if cnt > 0:
            reasons[reason] = reasons.get(reason, 0) + cnt
            valid_mask = valid_mask & ~mask

    # user_id 空
    _mark(df["user_id"].isna() | (df["user_id"].astype(str).str.strip() == ""), "user_id 为空")

    # event_time 空或无法解析（仅会话表有此列；用户总表是周报汇总无时间列）
    if "event_time" in df.columns and table_type == "sessions":
        time_parsed = pd.to_datetime(df["event_time"], errors="coerce")
        _mark(time_parsed.isna(), "event_time 为空或格式错误")

    # event_name 空（仅当存在该列时检查）
    if "event_name" in df.columns:
        _mark(df["event_name"].isna() | (df["event_name"].astype(str).str.strip() == ""), "event_name 为空")

    # 完全重复记录
    dup = df.duplicated(keep="first")
    _mark(dup, "完全重复记录")

    # 空问题文本（question_text 为空或纯符号）；仅当该列存在
    if "question_text" in df.columns:
        qt_raw = df["question_text"]
        # NaN 必须用 isna() 判断（pandas 3.0 astype(str) 后 NaN 变特殊字符串，== 比较失效）
        empty_q = qt_raw.isna() | (qt_raw.astype(str).str.strip().isin(["", "nan", "None", "null", "<NA>"]))
        # 纯符号检测：不含任何字母数字或中文字符
        pure_symbol = qt_raw.fillna("").astype(str).apply(
            lambda x: not bool(re.search(r"[0-9A-Za-z\u4e00-\u9fff]", x)) if isinstance(x, str) else False
        )
        _mark(empty_q | pure_symbol, "空问题或纯符号")

    # 超长文本（> MAX_TEXT_LENGTH），不排除但标记
    if "question_text" in df.columns:
        qt = df["question_text"].astype(str)
        overlong = qt.str.len() > config.MAX_TEXT_LENGTH
        if overlong.sum() > 0:
            rep.extra_info["overlong_text_count"] = int(overlong.sum())
            rep.extra_info["max_text_length"] = config.MAX_TEXT_LENGTH

    rep.excluded_count = int((~valid_mask).sum())
    rep.valid_count = int(valid_mask.sum())
    rep.exclude_reasons = reasons

    # 可做/不可做分析
    rep.available_analyses, rep.unavailable_analyses = _analysis_availability(df, table_type)

    return rep


def _analysis_availability(
    df: pd.DataFrame,
    table_type: str = "sessions",
) -> tuple[list[str], dict[str, list[str]]]:
    """根据表类型 + 字段判断可做/不可做分析（贴合真实周报/会话表）。"""
    avail: list[str] = []
    unavail: dict[str, list[str]] = {}

    def _need(name: str, fields: list[str], extra_note: str = ""):
        missing = [f for f in fields if f not in df.columns]
        if missing:
            unavail[name] = missing + ([extra_note] if extra_note else [])
        else:
            avail.append(name)

    if table_type == "users":
        avail.append("用户分群与分层")
        if "upload_count" in df.columns:
            avail.append("上传图纸汇总")
        else:
            unavail["上传图纸汇总"] = ["upload_count"]
        if "next_action" in df.columns:
            avail.append("周报行动建议")
        if "issue_summary" in df.columns or "new_demand_summary" in df.columns:
            avail.append("新需求与问题跟进")
        if "question_text" in df.columns:
            avail.append("高频问题与真实问法")
        return avail, unavail

    avail.append("用户与提问概览")
    if "question_text" in df.columns:
        avail.append("高频问题与真实问法")
        avail.append("问答漏斗（提问→回答→图纸）")
        avail.append("会话问法路径")
    else:
        unavail["高频问题与真实问法"] = ["question_text"]

    _need("会话内重复提问", ["session_id"], "缺少会话ID字段")
    if "upload_file_type" in df.columns or "upload_count" in df.columns:
        avail.append("上传图纸采用")
    else:
        unavail["上传图纸采用"] = ["upload_file_type", "upload_count"]

    _need("识别成功率", ["recognized_intent", "intent_confidence"], "缺少识别意图或置信度字段")
    _need("有效回答率", ["answer_status"], "缺少回答状态字段")
    if "page_name" in df.columns or "event_name" in df.columns:
        avail.append("页面路径分析")
    else:
        unavail["埋点页面路径"] = ["page_name", "event_name", "真实会话表按提问序列做路径"]
    if "feature_name" in df.columns:
        avail.append("功能采用分析")
    elif "upload_file_type" in df.columns:
        avail.append("图纸类型采用（无 feature_name 时的替代）")
    else:
        unavail["功能采用分析"] = ["feature_name"]
    if "event_name" in df.columns:
        avail.append("埋点行为漏斗")
    else:
        unavail["埋点行为漏斗"] = ["event_name", "已改用问答漏斗"]

    return avail, unavail


def ingest(
    path: str | Path,
    table_type: str,
    file_name: str = "",
) -> tuple[pd.DataFrame, QualityReport]:
    """完整导入流程：读取 → 清洗 → 映射 → 质检 → 存批次（去重）。

    返回 (清洗后的 DataFrame, 质量报告)。
    """
    p = Path(path)
    df = load_file(p)
    df = clean_empty_columns(df)
    df = map_fields(df)
    df = normalize_user_dimension(df)

    fh = file_hash(p)
    rep = quality_check(df, table_type, file_name or p.name)
    rep.extra_info["file_hash"] = fh

    # 去重：若已存在同哈希批次，标记但允许重新读取
    try:
        is_dup = storage.batch_exists(fh)
    except Exception:
        try:
            storage.init_db()
            is_dup = storage.batch_exists(fh)
        except Exception:
            is_dup = False
    rep.extra_info["duplicate"] = is_dup

    # 保存批次（仅当非重复且有效）
    if not is_dup and rep.valid_count >= 0:
        try:
            storage.insert_batch(
                week_label=rep.week_label,
                file_name=file_name or p.name,
                file_hash=fh,
                table_type=table_type,
                row_count=rep.raw_count,
                valid_count=rep.valid_count,
                excluded_count=rep.excluded_count,
            )
        except Exception:
            # 哈希冲突等，不阻塞
            pass

    return df, rep
