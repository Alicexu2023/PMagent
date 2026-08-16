"""tests/conftest.py — 测试夹具：构造临时样例数据。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

# 让 tests 能导入项目模块
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def sample_sessions_df() -> pd.DataFrame:
    """构造会话表样例（含必需 + 建议字段）。"""
    data = {
        "user_id": ["u1", "u1", "u2", "u2", "u3", "u3", "u4"],
        "event_time": [
            "2026-08-01 10:00:00",
            "2026-08-01 10:05:00",
            "2026-08-01 11:00:00",
            "2026-08-02 09:00:00",
            "2026-08-03 10:00:00",
            "2026-08-03 10:01:00",
            "2026-08-05 10:00:00",
        ],
        "event_name": [
            "进入智能体", "提问", "提问", "获得回答",
            "提问", "提问", "提问",
        ],
        "question_id": ["q1", "q2", "q3", "q4", "q5", "q6", "q7"],
        "question_text": [
            "如何查看订单", "订单在哪里", "如何查看订单",
            "库存怎么查", "如何查看订单", "如何查看订单", "",
        ],
        "session_id": ["s1", "s1", "s2", "s2", "s3", "s3", "s4"],
        "recognized_intent": [
            "订单查询", "订单查询", "订单查询",
            "库存查询", "订单查询", "订单查询", "",
        ],
        "intent_confidence": ["0.9", "0.8", "0.7", "0.9", "0.5", "0.85", "0.1"],
        "answer_status": ["成功", "成功", "成功", "成功", "失败", "成功", "失败"],
        "page_name": ["首页", "订单页", "首页", "库存页", "首页", "首页", "首页"],
        "feature_name": ["订单", "订单", "订单", "库存", "订单", "订单", ""],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_users_df() -> pd.DataFrame:
    """用户总表样例。"""
    data = {
        "user_id": ["u1", "u2", "u3", "u4"],
        "role": ["采购", "仓管", "采购", "管理员"],
        "factory": ["A厂", "B厂", "A厂", "C厂"],
    }
    return pd.DataFrame(data)
