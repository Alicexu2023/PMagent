"""analysis/insights.py — AI 结论生成 + 数字证据校验 + 报告导出。

统一结构：结论 / 数据证据 / 影响 / 原因判断（已证实/待验证）/ 下一步动作 / 优先级 / 置信度。
AI 输出中的每个数字必须能在本地指标中找到，校验失败的内容不进入正式结论。
"""
from __future__ import annotations

import json
import re
from typing import Any

from analysis import ai_client
from analysis.product import generate_local_conclusion as _local_conclusion
from core import storage


def build_metrics_payload(metrics: dict[str, float | int]) -> str:
    """把本地指标汇总成发给模型的文本（只发汇总指标）。"""
    lines = []
    for k, v in metrics.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def generate_conclusion(
    metrics: dict[str, float | int],
    sample_questions: list[str] | None = None,
    extra_context: str = "",
) -> tuple[dict | None, str | None]:
    """调用 AI 生成结论（含证据校验）。

    返回 (结论 dict, error)。
    """
    if not metrics:
        return None, "无本地指标，无法生成结论"

    sample = ai_client.desensitize_sample(sample_questions or [], 15)
    payload = build_metrics_payload(metrics)

    system = (
        "你是工厂智能体数据分析助手。基于给定的本地计算结果生成分析结论。\n"
        "严格要求：\n"
        "1. 结论中的每个数字必须来自给定的本地指标，不得编造。\n"
        "2. 原因判断区分『数据已支持』与『待验证假设』。\n"
        "3. 下一步动作要可执行，禁止空话（如'持续优化体验'）。\n"
        "4. 只用 JSON 输出，结构如下：\n"
        '{"结论":"...","数据证据":"...","影响":"...","原因判断":{"数据已支持":"...","待验证假设":"..."},'
        '"下一步动作":[{"动作":"...","优先级":"P0/P1/P2","目标指标":"..."}],'
        '"置信度":{"等级":"高/中/低","理由":"..."}}'
    )
    user = (
        f"本地指标：\n{payload}\n"
        + (f"\n代表问法样本（已脱敏）：\n" + "\n".join(f"- {s}" for s in sample) + "\n" if sample else "")
        + (f"\n补充背景：\n{extra_context}\n" if extra_context else "")
        + "\n请生成分析结论。"
    )

    content, err = ai_client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        json_mode=True,
    )
    if err:
        return None, err

    data, parse_err = ai_client.parse_json_response(content)
    if parse_err:
        return None, parse_err

    # 证据校验：可疑数字标警告，不再整段丢弃（否则正常产品表述几乎都会被拦截）
    conclusion_text = (data.get("结论", "") or "") + " " + (data.get("数据证据", "") or "")
    ok, not_found = ai_client.validate_evidence(conclusion_text, metrics)
    if not ok:
        data["证据警告"] = f"以下数字未在本地指标中找到，请人工核对：{', '.join(not_found)}"
    data.setdefault("来源", "模型")
    return data, None


def generate_local_conclusion(df_sessions, df_users=None) -> dict:
    """无模型时的正式结论。"""
    return _local_conclusion(df_sessions, df_users)


def generate_cluster(
    sample_questions: list[str],
) -> tuple[dict | None, str | None]:
    """AI 问法聚类：真实问法 -> 标准问题命名 + 同义表达。"""
    if not sample_questions:
        return None, "无问法样本，无法聚类"

    sample = ai_client.desensitize_sample(sample_questions, 30)
    system = (
        "你是工厂智能体意图分析助手。对用户真实问法做聚类和标准问题命名。\n"
        "只用 JSON 输出，格式：\n"
        '{"标准问题":[{"标准问题名称":"...","包含问法":["..."],"建议意图":"...","理由":"..."}]}'
    )
    user = "真实问法样本（已脱敏）：\n" + "\n".join(f"- {s}" for s in sample) + "\n请聚类。"
    content, err = ai_client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        json_mode=True,
    )
    if err:
        return None, err
    return ai_client.parse_json_response(content)


def generate_synonyms(
    std_question: str,
    sample_questions: list[str],
) -> tuple[list[dict] | None, str | None]:
    """AI 生成同义表达建议。"""
    if not sample_questions:
        return None, "无问法样本"

    sample = ai_client.desensitize_sample(sample_questions, 20)
    system = (
        "你是工厂智能体同义表达分析助手。为给定的标准问题生成同义表达建议。\n"
        "只用 JSON 输出，格式：\n"
        '{"同义表达":[{"原始问法":"...","建议标准问题":"...","建议意图":"...","建议理由":"..."}]}'
    )
    user = (
        f"标准问题：{std_question}\n"
        "真实问法样本（已脱敏）：\n" + "\n".join(f"- {s}" for s in sample) + "\n请生成同义表达建议。"
    )
    content, err = ai_client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        json_mode=True,
    )
    if err:
        return None, err
    data, parse_err = ai_client.parse_json_response(content)
    if parse_err:
        return None, parse_err
    return data.get("同义表达", []), None


def generate_review_summary(
    compare: dict[str, dict],
) -> tuple[dict | None, str | None]:
    """效果回看摘要：改善/无明显变化/变差。"""
    if not compare:
        return None, "无对比数据"

    system = (
        "你是工厂智能体数据分析助手。基于动作前后指标对比，判定改善/无明显变化/变差。\n"
        "只用 JSON 输出：{\"判定\":\"改善|无明显变化|变差\",\"摘要\":\"...\",\"理由\":\"...\"}\n"
        "摘要中的数字必须来自给定对比数据，不得编造。"
    )
    lines = []
    for metric, d in compare.items():
        lines.append(f"- {metric}: 动作前 {d.get('动作前')}, 动作后 {d.get('动作后')}, 差值 {d.get('差值')}")
    user = "指标对比：\n" + "\n".join(lines) + "\n请判定。"
    content, err = ai_client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        json_mode=True,
    )
    if err:
        return None, err
    return ai_client.parse_json_response(content)


# ---------------------------------------------------------------------------
# 报告导出
# ---------------------------------------------------------------------------
def build_markdown_report(
    summary: str,
    core_data: dict[str, float | int],
    main_problems: list[str],
    cause_judgment: str,
    next_actions: list[dict],
) -> str:
    """生成 Markdown 报告初稿（5 章节）。"""
    lines = ["# 工厂智能体分析报告", ""]
    lines.append("## 一、结论摘要")
    lines.append(summary or "（无）")
    lines.append("")
    lines.append("## 二、核心数据")
    if core_data:
        for k, v in core_data.items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## 三、主要问题")
    if main_problems:
        for p in main_problems:
            lines.append(f"- {p}")
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## 四、原因判断")
    lines.append(cause_judgment or "（无）")
    lines.append("")
    lines.append("## 五、下一步动作")
    if next_actions:
        for a in next_actions:
            action = a.get("动作", "")
            prio = a.get("优先级", "")
            metric = a.get("目标指标", "")
            lines.append(f"- [{prio}] {action}" + (f"（目标指标：{metric}）" if metric else ""))
    else:
        lines.append("（无）")
    lines.append("")
    return "\n".join(lines)


def export_synonyms_csv(synonyms: list[dict]) -> str:
    """把同义表达导出为 CSV 文本。"""
    import io
    import csv
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["原始问法", "建议标准问题", "建议意图", "建议理由", "来源频次", "影响人数"])
    for s in synonyms:
        writer.writerow([
            s.get("raw_text", ""),
            s.get("std_question", ""),
            s.get("intent", ""),
            s.get("reason", ""),
            s.get("freq", ""),
            s.get("affected_users", ""),
        ])
    return buf.getvalue()
