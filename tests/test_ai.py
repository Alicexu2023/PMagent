"""tests/test_ai.py — 脱敏与证据校验测试。"""
from __future__ import annotations

from analysis import ai_client


def test_desensitize_phone():
    out = ai_client.desensitize("请联系 13800138000")
    assert "13800138000" not in out
    assert "[手机号]" in out


def test_desensitize_email():
    out = ai_client.desensitize("邮箱 a@b.com")
    assert "a@b.com" not in out
    assert "[邮箱]" in out


def test_extract_numbers():
    nums = ai_client.extract_numbers("共 123 人，占比 45.6%")
    assert 123.0 in nums
    assert 45.6 in nums


def test_validate_evidence_pass():
    text = "本次共有 100 个用户"
    metrics = {"用户数": 100}
    ok, not_found = ai_client.validate_evidence(text, metrics)
    assert ok is True
    assert not_found == []


def test_validate_evidence_fail():
    """反向验证：AI 编造本地不存在的数字，必须被拦截。"""
    text = "本次共有 99999 个用户"  # 本地指标只有 100
    metrics = {"用户数": 100}
    ok, not_found = ai_client.validate_evidence(text, metrics)
    assert ok is False
    assert "99999" in not_found or any("99999" in n for n in not_found)


def test_validate_evidence_ignores_small_numbers():
    # 1、0 等小数字不误报
    text = "第 1 步，优先级 P0"
    metrics = {"用户数": 100}
    ok, _ = ai_client.validate_evidence(text, metrics)
    assert ok is True
