"""用 lists/ 真实样表做回归，避免只对虚构埋点数据测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from analysis import funnel, ingestion, insights, paths, product, questions as q
from analysis.adoption import upload_type_adoption

ROOT = Path(__file__).resolve().parent.parent
LISTS = ROOT / "lists"


def _find(pattern: str) -> Path | None:
    if not LISTS.exists():
        return None
    hits = list(LISTS.glob(pattern))
    return hits[0] if hits else None


@pytest.fixture(scope="module")
def _iso_db(tmp_path_factory):
    import core.config as cfg
    from core import storage
    path = tmp_path_factory.mktemp("db") / "real.sqlite"
    prev = cfg.DB_PATH
    cfg.DB_PATH = path
    storage.init_db()
    yield path
    cfg.DB_PATH = prev


@pytest.fixture(scope="module")
def real_users(_iso_db):
    p = _find("*用户总表*.csv")
    if p is None:
        pytest.skip("lists/ 中没有用户总表")
    df, rep = ingestion.ingest(p, "users", p.name)
    return df, rep


@pytest.fixture(scope="module")
def real_sessions(_iso_db):
    p = _find("*会话*.csv")
    if p is None:
        pytest.skip("lists/ 中没有会话表")
    df, rep = ingestion.ingest(p, "sessions", p.name)
    return df, rep


def test_real_users_mapped(real_users):
    df, rep = real_users
    assert rep.valid_count == 370
    assert "user_id" in df.columns
    assert "next_action" in df.columns
    assert "issue_summary" in df.columns
    assert "高频问题与真实问法" not in rep.available_analyses
    assert "周报行动建议" in rep.available_analyses


def test_real_sessions_mapped(real_sessions):
    df, rep = real_sessions
    assert rep.raw_count == 3000
    assert "user_id" in df.columns
    assert "question_text" in df.columns
    assert "event_name" not in df.columns
    assert "高频问题与真实问法" in rep.available_analyses
    assert "问答漏斗（提问→回答→图纸）" in rep.available_analyses


def test_real_intents_not_raw_dump(real_sessions):
    df, _ = real_sessions
    hf = q.high_freq_questions(df)
    assert not hf.empty
    assert len(hf) < 30
    assert "成本报价" in set(hf["标准问题"])
    quote = hf[hf["标准问题"] == "成本报价"].iloc[0]
    assert int(quote["提问次数"]) >= 40


def test_real_clean_not_json(real_sessions):
    df, _ = real_sessions
    exact = q.exact_questions(df, top_n=20)
    assert not exact.empty
    assert not exact["问法"].astype(str).str.contains("零件文件预处理上下文").any()


def test_real_qa_funnel(real_sessions):
    df, _ = real_sessions
    f = funnel.qa_funnel(df)
    assert list(f["步骤"]) == ["进入并留下记录", "发起有效提问", "获得实质回答", "上传真实图纸"]
    assert int(f.iloc[0]["达标用户数"]) == 371
    assert int(f.iloc[-1]["达标用户数"]) < int(f.iloc[0]["达标用户数"])


def test_real_question_paths(real_sessions):
    df, _ = real_sessions
    p = paths.build_paths(df, before=2, after=2)
    assert not p.empty
    top = paths.top_paths(p)
    assert not top.empty


def test_real_upload_adoption_excludes_none(real_sessions):
    df, _ = real_sessions
    a = upload_type_adoption(df)
    assert not a.empty
    assert not any(str(x) in {"无", "none"} for x in a["功能"])
    assert int(a["使用次数"].sum()) > 1000


def test_real_local_conclusion(real_users, real_sessions):
    dfu, _ = real_users
    dfs, _ = real_sessions
    data = insights.generate_local_conclusion(dfs, dfu)
    assert data["来源"] == "本地规则"
    assert "工厂" in data["结论"]
    assert data["下一步动作"]
    assert any(a.get("优先级") == "P0" for a in data["下一步动作"])
    metrics = product.collect_metrics(dfs, dfu)
    assert metrics["有效提问数"] >= 2800
    assert metrics["问题工厂数"] >= 1
    assert metrics.get("上传图纸次数", 0) < 3000
