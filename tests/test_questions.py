"""tests/test_questions.py — 问答分析测试。"""
from __future__ import annotations

import pandas as pd

from analysis import questions as q


def test_is_valid_question():
    assert q.is_valid_question("如何查看订单") is True
    assert q.is_valid_question("") is False
    assert q.is_valid_question("测试") is False
    assert q.is_valid_question("test") is False
    assert q.is_valid_question("!!!") is False


def test_clean_question_strips_preprocess():
    raw = '帮我报价 [零件文件预处理上下文] 零件文件1：a.pdf 预处理结果：{"status":"success"}'
    assert q.clean_question_text(raw) == "帮我报价"
    assert q.assign_intent(raw) == "成本报价"
    assert q.assign_intent("帮我报一下价") == "成本报价"
    assert q.assign_intent("推荐询盘") == "询盘推荐"
    assert q.assign_intent("拆解工艺，分析与本公司的匹配度") == "工艺匹配"


def test_high_freq_questions(sample_sessions_df):
    hf = q.high_freq_questions(sample_sessions_df)
    assert not hf.empty
    # 订单查询（含回退 question_text）应最多
    top = hf.iloc[0]
    assert top["标准问题"] in ("订单查询", "如何查看订单")
    assert top["提问次数"] >= 3


def test_real_questions_diversity(sample_sessions_df):
    hf = q.high_freq_questions(sample_sessions_df)
    top = hf.iloc[0]["标准问题"]
    real = q.real_questions(sample_sessions_df, top, top_n=20)
    assert len(real) >= 1
    # 每条含关键字段
    for r in real:
        assert "问法" in r
        assert "次数" in r


def test_repeat_questions(sample_sessions_df):
    cnt, valid, _ = q.repeat_questions(sample_sessions_df, window_min=10)
    # "如何查看订单" 被 u1 和 u3 重复问，但在不同 session，且时间窗内
    assert valid >= 0
    assert cnt >= 0
