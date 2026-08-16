"""tests/test_analytics.py — 漏斗/留存/路径/功能采用测试。"""
from __future__ import annotations

import pandas as pd

from analysis import funnel, retention, paths, adoption


def test_funnel(sample_sessions_df):
    f = funnel.funnel_analysis(sample_sessions_df)
    assert not f.empty
    assert list(f.columns) == ["步骤", "达标用户数", "转化率(%)", "流失率(%)"]
    # 第一步进入智能体 1 人（u1）
    assert f.iloc[0]["达标用户数"] == 1


def test_retention(sample_sessions_df):
    r, note = retention.retention_analysis(sample_sessions_df)
    assert not r.empty
    assert "D1" in r["周期"].tolist()
    # 样本 4 人 < 30，应标注样本不足
    assert "样本不足" in note


def test_paths(sample_sessions_df):
    p = paths.build_paths(sample_sessions_df, before=2, after=2)
    assert not p.empty
    assert "full_path" in p.columns


def test_paths_noise_exclusion(sample_sessions_df):
    # 加入噪声事件
    df = sample_sessions_df.copy()
    noise = pd.DataFrame({
        "user_id": ["u1"], "event_time": ["2026-08-01 09:00:00"],
        "event_name": ["心跳"], "question_id": [""], "question_text": [""],
        "session_id": ["s1"], "page_name": ["系统"], "feature_name": [""],
    })
    df = pd.concat([df, noise], ignore_index=True)
    p = paths.build_paths(df, before=2, after=2, exclude_noise=["心跳"])
    assert not p.empty
    # 噪声节点不应出现在路径中
    assert all("心跳" not in fp for fp in p["full_path"])


def test_adoption(sample_sessions_df):
    a = adoption.adoption_analysis(sample_sessions_df)
    assert not a.empty
    # 订单功能使用人数 >= 2
    order_row = a[a["功能"] == "订单"]
    if not order_row.empty:
        assert order_row.iloc[0]["使用人数"] >= 2
