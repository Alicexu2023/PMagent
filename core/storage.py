"""core/storage.py — SQLite 存储层：数据集批次、AI 结论、行动清单、指标快照。

零配置单文件 SQLite。个人使用不需要审计与口径版本。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _db_path() -> Path:
    """每次读取当前配置，避免测试 monkeypatch 不到已绑定的模块常量。"""
    from core import config
    return config.DB_PATH


def get_conn() -> sqlite3.Connection:
    """获取 SQLite 连接，开启外键与行工厂。"""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL,          -- 周次标识，如 2026-W33
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    table_type TEXT NOT NULL,          -- users / sessions / feedback
    row_count INTEGER,
    valid_count INTEGER,
    excluded_count INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(file_hash)
);

CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    content TEXT NOT NULL,             -- JSON: 结论/证据/影响/原因/动作/优先级/置信度
    created_at TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES batches(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    problem TEXT NOT NULL,             -- 问题
    evidence TEXT,                     -- 证据
    priority TEXT,                     -- P0/P1/P2
    suggested_action TEXT,             -- 建议动作
    target_metric TEXT,                -- 目标指标
    status TEXT NOT NULL DEFAULT '待评估',  -- 待评估/处理中/待回看/已完成/已关闭
    review_time TEXT,                  -- 预计回看时间
    snapshot TEXT,                     -- JSON: 动作前指标快照
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS synonyms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_text TEXT NOT NULL,            -- 原始问法
    std_question TEXT,                 -- 建议标准问题
    intent TEXT,                       -- 建议意图
    reason TEXT,                       -- 建议理由
    freq INTEGER DEFAULT 0,            -- 来源频次
    affected_users INTEGER DEFAULT 0,  -- 影响人数
    edited INTEGER DEFAULT 0,          -- 是否人工修改
    created_at TEXT NOT NULL
);
"""


def init_db() -> None:
    """初始化数据库表结构。"""
    _db_path().parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 批次
# ---------------------------------------------------------------------------
def insert_batch(
    week_label: str,
    file_name: str,
    file_hash: str,
    table_type: str,
    row_count: int,
    valid_count: int,
    excluded_count: int,
) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO batches(week_label, file_name, file_hash, table_type, "
            "row_count, valid_count, excluded_count, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (week_label, file_name, file_hash, table_type,
             row_count, valid_count, excluded_count, _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def batch_exists(file_hash: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM batches WHERE file_hash=? LIMIT 1", (file_hash,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def list_batches() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM batches ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 行动清单
# ---------------------------------------------------------------------------
def insert_action(
    problem: str,
    evidence: str | None,
    priority: str,
    suggested_action: str,
    target_metric: str | None,
    review_time: str | None,
    snapshot: dict | None = None,
) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO actions(problem, evidence, priority, suggested_action, "
            "target_metric, status, review_time, snapshot, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (problem, evidence, priority, suggested_action, target_metric,
             "待评估", review_time,
             json.dumps(snapshot, ensure_ascii=False) if snapshot else None,
             _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_actions() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM actions ORDER BY id DESC"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("snapshot"):
                d["snapshot"] = json.loads(d["snapshot"])
            out.append(d)
        return out
    finally:
        conn.close()


def update_action_status(action_id: int, status: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE actions SET status=? WHERE id=?", (status, action_id)
        )
        conn.commit()
    finally:
        conn.close()


def update_action(action_id: int, **fields) -> None:
    """按传入字段更新行动项。"""
    if not fields:
        return
    allowed = {"problem", "evidence", "priority", "suggested_action",
               "target_metric", "status", "review_time", "snapshot"}
    sets = []
    vals = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "snapshot" and v is not None:
            v = json.dumps(v, ensure_ascii=False)
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return
    vals.append(action_id)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE actions SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
    finally:
        conn.close()


def delete_action(action_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM actions WHERE id=?", (action_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# AI 结论
# ---------------------------------------------------------------------------
def insert_insight(content: dict, batch_id: int | None = None) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO insights(batch_id, content, created_at) VALUES(?,?,?)",
            (batch_id, json.dumps(content, ensure_ascii=False), _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_insights() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM insights ORDER BY id DESC"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["content"] = json.loads(d["content"])
            out.append(d)
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 同义表达
# ---------------------------------------------------------------------------
def upsert_synonym(
    raw_text: str, std_question: str | None, intent: str | None,
    reason: str | None, freq: int, affected_users: int, edited: int = 0,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO synonyms(raw_text, std_question, intent, reason, freq, "
            "affected_users, edited, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (raw_text, std_question, intent, reason, freq, affected_users, edited, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_synonyms() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM synonyms ORDER BY freq DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_synonym(syn_id: int, **fields) -> None:
    allowed = {"raw_text", "std_question", "intent", "reason", "freq",
               "affected_users", "edited"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return
    vals.append(syn_id)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE synonyms SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
    finally:
        conn.close()


def delete_synonym(syn_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM synonyms WHERE id=?", (syn_id,))
        conn.commit()
    finally:
        conn.close()
