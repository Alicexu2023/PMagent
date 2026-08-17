"""analysis/ai_client.py — DeepSeek / OpenAI 兼容客户端 + 脱敏 + 证据校验。

- 发送前脱敏（手机号/邮箱/公司名）
- 只发送汇总指标和必要代表问法，不发送整表
- 无 Key / 超时 / 非法 JSON 时本地结果不丢失
- 证据校验：AI 输出中的数字必须在本地指标中找到，否则拦截
"""
from __future__ import annotations

import json
import re
from typing import Any

from core import config

# ---------------------------------------------------------------------------
# 脱敏
# ---------------------------------------------------------------------------
PHONE_RE = re.compile(r"1[3-9]\d{9}")                     # 手机号
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 公司名/敏感词表（可扩展）
COMPANY_RE = re.compile(r"(某某公司|XX公司|示例公司|测试公司)")


def desensitize(text: str, extra_terms: list[str] | None = None) -> str:
    """对文本做正则脱敏，并可替换真实公司名。"""
    if not text:
        return text
    t = PHONE_RE.sub("[手机号]", text)
    t = EMAIL_RE.sub("[邮箱]", t)
    t = COMPANY_RE.sub("[公司]", t)
    if extra_terms:
        for term in sorted({str(x).strip() for x in extra_terms if x}, key=len, reverse=True):
            if len(term) >= 2:
                t = t.replace(term, "[公司]")
    return t


def desensitize_sample(
    texts: list[str],
    max_items: int = 20,
    extra_terms: list[str] | None = None,
) -> list[str]:
    """对代表问法样本脱敏，且只取前 max_items 条（最少样本）。"""
    out = []
    for t in texts[:max_items]:
        out.append(desensitize(str(t), extra_terms=extra_terms))
    return out


# ---------------------------------------------------------------------------
# AI 客户端（OpenAI 兼容）
# ---------------------------------------------------------------------------
def _client():
    if not config.has_api_key():
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL)
    except Exception:
        return None


def chat(
    messages: list[dict],
    json_mode: bool = False,
) -> tuple[str | None, str | None]:
    """调用模型。返回 (content, error)。

    json_mode=True 时要求返回 JSON。
    """
    if not config.has_api_key():
        return None, "未配置 DeepSeek API Key，AI 功能不可用（本地分析不受影响）"

    client = _client()
    if client is None:
        return None, "OpenAI 客户端初始化失败"

    try:
        kwargs: dict[str, Any] = {
            "model": config.DEEPSEEK_MODEL,
            "messages": messages,
            "timeout": config.AI_TIMEOUT_SECONDS,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content
        return content, None
    except Exception as e:
        msg = str(e)
        if "timeout" in msg.lower() or "timed out" in msg.lower():
            return None, "模型调用超时，请稍后重试"
        return None, f"模型调用失败: {msg[:200]}"


def parse_json_response(content: str | None) -> tuple[dict | None, str | None]:
    """解析模型返回的 JSON；非法 JSON 返回错误。"""
    if content is None:
        return None, "模型无返回内容"
    # 尝试直接解析
    try:
        return json.loads(content), None
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json ... ``` 代码块
    m = re.search(r"```json\s*(.*?)```", content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1)), None
        except json.JSONDecodeError:
            pass
    # 尝试提取第一个 {...}
    m2 = re.search(r"\{.*\}", content, re.DOTALL)
    if m2:
        try:
            return json.loads(m2.group(0)), None
        except json.JSONDecodeError:
            pass
    return None, "模型返回非法 JSON，无法解析"


# ---------------------------------------------------------------------------
# 证据校验（质量门禁）
# ---------------------------------------------------------------------------
def extract_numbers(text: str) -> list[float]:
    """提取文本中的数字。"""
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    return [float(n) for n in nums]


def validate_evidence(
    conclusion_text: str,
    local_metrics: dict[str, float | int],
) -> tuple[bool, list[str]]:
    """校验结论中的数字是否能在本地指标中找到。

    返回 (是否通过, 未找到的数字列表)。

    规则：结论中出现的整数（>1 的数量级数字）必须在 local_metrics 的值集合中出现；
    百分比/小数允许一定误差。
    """
    numbers = extract_numbers(conclusion_text)
    metric_values = [float(v) for v in local_metrics.values() if isinstance(v, (int, float))]
    not_found = []
    for n in numbers:
        # 序数、Top N、优先级、日期天数
        if n <= 31:
            continue
        # 年份
        if 2000 <= n <= 2100 and float(n).is_integer():
            continue
        found = False
        for mv in metric_values:
            if abs(mv - n) <= max(0.5, abs(mv) * 0.001):
                found = True
                break
        if not found:
            not_found.append(str(n))
    return (len(not_found) == 0), not_found
