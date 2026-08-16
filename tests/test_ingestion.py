"""tests/test_ingestion.py — 数据导入与质量门禁测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from analysis import ingestion


def test_normalize_column():
    assert ingestion.normalize_column("user_id") == "user_id"
    assert ingestion.normalize_column("用户ID") == "user_id"
    assert ingestion.normalize_column(" 提问内容 ") == "question_text"
    assert ingestion.normalize_column("event_name") == "event_name"


def test_clean_empty_columns():
    df = pd.DataFrame({"a": ["1"], "Unnamed: 1": [None]})
    out = ingestion.clean_empty_columns(df)
    assert "Unnamed: 1" not in out.columns


def test_map_fields():
    df = pd.DataFrame({"用户ID": ["u1"], "提问内容": ["x"], "事件名": ["ask"]})
    out = ingestion.map_fields(df)
    assert "user_id" in out.columns
    assert "question_text" in out.columns
    assert "event_name" in out.columns


def test_quality_check_valid(sample_sessions_df):
    rep = ingestion.quality_check(sample_sessions_df, "sessions")
    assert rep.raw_count == 7
    # 第 7 条 question_text 为空，被"空问题"排除
    assert rep.valid_count == 6
    assert rep.excluded_count == 1
    assert "空问题或纯符号" in rep.exclude_reasons


def test_quality_check_pure_symbol():
    df = pd.DataFrame({
        "user_id": ["u1"],
        "event_time": ["2026-08-01 10:00:00"],
        "event_name": ["提问"],
        "question_text": ["!!!"],
    })
    rep = ingestion.quality_check(df, "sessions")
    assert rep.valid_count == 0
    assert rep.excluded_count == 1
    assert "空问题或纯符号" in rep.exclude_reasons


def test_quality_check_missing_required():
    df = pd.DataFrame({"a": ["1"], "b": ["2"]})
    rep = ingestion.quality_check(df, "sessions")
    assert rep.missing_required == ["user_id", "event_time"]
    assert rep.valid_count == 0
    assert rep.available_analyses == []


def test_reverse_missing_factory_id():
    """反向验证：缺工厂ID(user_id) 时导入失败并显示原因。"""
    df = pd.DataFrame({
        "event_time": ["2026-08-01 10:00:00"],
        "question_text": ["如何查看订单"],
    })
    rep = ingestion.quality_check(df, "sessions")
    assert "user_id" in rep.missing_required
    assert rep.valid_count == 0
    assert rep.unavailable_analyses  # 全部分析不可用


def test_reverse_missing_event_time():
    """反向验证：缺提问时间(event_time) 时导入失败并显示原因。"""
    df = pd.DataFrame({
        "user_id": ["u1"],
        "question_text": ["如何查看订单"],
    })
    rep = ingestion.quality_check(df, "sessions")
    assert "event_time" in rep.missing_required
    assert rep.valid_count == 0


def test_reverse_restore_green():
    """反向验证：补齐字段后恢复全绿。"""
    df = pd.DataFrame({
        "user_id": ["u1"],
        "event_time": ["2026-08-01 10:00:00"],
        "question_text": ["如何查看订单"],
    })
    rep = ingestion.quality_check(df, "sessions")
    assert rep.missing_required == []
    assert rep.valid_count == 1
    assert "高频问题与真实问法" in rep.available_analyses


def test_quality_check_feedback_empty():
    df = pd.DataFrame()
    rep = ingestion.quality_check(df, "feedback")
    assert rep.valid_count == 0
    assert "反馈表为空" in rep.extra_info.get("note", "")


def test_detect_week_label(sample_sessions_df):
    week = ingestion.detect_week_label(sample_sessions_df)
    assert week.startswith("2026-W")
