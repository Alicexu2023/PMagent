"""analysis/product.py — 面向真实周报+会话表的本地产品分析。

不依赖埋点事件，不依赖 API Key。数字全部 pandas 计算。
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from analysis import questions as q
from analysis import retention


YES_VALUES = {"是", "Y", "y", "1", "true", "True", "yes", "YES"}
NO_UPLOAD = {"", "无", "没有", "none", "nan", "null", "无文件", "-", "—"}


def is_yes(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().isin(YES_VALUES)


def is_real_upload(value) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    t = str(value).strip().lower()
    return t not in {x.lower() for x in NO_UPLOAD}


def _nunique(df: pd.DataFrame, col: str) -> int:
    if df is None or df.empty or col not in df.columns:
        return 0
    return int(df[col].nunique())


def upload_mask(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty or "upload_file_type" not in df.columns:
        return pd.Series(False, index=getattr(df, "index", None))
    return df["upload_file_type"].map(is_real_upload)


def collect_metrics(
    df_sessions: pd.DataFrame | None,
    df_users: pd.DataFrame | None = None,
) -> dict[str, float | int]:
    """客观指标：给首页、报告、模型共用。"""
    metrics: dict[str, float | int] = {}
    df = df_sessions

    if df is not None and not df.empty:
        metrics["事件总数"] = int(len(df))
        metrics["用户数"] = _nunique(df, "user_id")
        metrics["工厂数"] = _nunique(df, "user_id")
        metrics["会话数"] = _nunique(df, "session_id")
        if "question_text" in df.columns:
            valid = df["question_text"].map(q.is_valid_question)
            metrics["有效提问数"] = int(valid.sum())
        else:
            valid = pd.Series(False, index=df.index)
            metrics["有效提问数"] = 0

        if "upload_file_type" in df.columns:
            um = upload_mask(df)
            metrics["上传图纸次数"] = int(um.sum())
            metrics["上传图纸工厂数"] = int(df.loc[um, "user_id"].nunique()) if "user_id" in df.columns else 0
            total = max(int(len(df)), 1)
            metrics["提问附带图纸率(%)"] = round(um.sum() / total * 100, 2)
            no_file = int((~um).sum())
            metrics["未传图纸次数"] = no_file

        if "answer_text" in df.columns:
            ans = df["answer_text"].fillna("").astype(str).str.strip()
            metrics["有回答数"] = int((ans.str.len() >= 20).sum())
            total_q = metrics.get("有效提问数") or len(df)
            metrics["有回答率(%)"] = round(metrics["有回答数"] / total_q * 100, 2) if total_q else 0.0

        hf = q.high_freq_questions(df)
        if not hf.empty:
            for _, row in hf.iterrows():
                name = str(row["标准问题"])
                metrics[f"{name}提问数"] = int(row["提问次数"])
                metrics[f"{name}占比(%)"] = float(row["占比"])
            other = hf[hf["标准问题"] == q.OTHER_INTENT]
            if not other.empty:
                metrics["未归类提问数"] = int(other.iloc[0]["提问次数"])
                metrics["未归类占比(%)"] = float(other.iloc[0]["占比"])

        rep_cnt, valid_cnt, _ = q.repeat_questions(df)
        metrics["重复提问数"] = int(rep_cnt)
        if valid_cnt:
            metrics["重复提问率(%)"] = round(rep_cnt / valid_cnt * 100, 2)

        ret_df, _note = retention.retention_analysis(df)
        if not ret_df.empty:
            d1 = ret_df[ret_df["周期"] == "D1"]
            if not d1.empty and pd.notna(d1.iloc[0]["留存率(%)"]):
                metrics["D1留存率(%)"] = float(d1.iloc[0]["留存率(%)"])
                metrics["D1留存人数"] = int(d1.iloc[0]["留存人数"])

    if df_users is not None and not df_users.empty:
        metrics["用户总表工厂数"] = _nunique(df_users, "user_id") or _nunique(df_users, "factory_id")
        if "is_new" in df_users.columns:
            metrics["新用户数"] = int(is_yes(df_users["is_new"]).sum())
        if "is_return" in df_users.columns:
            metrics["回流用户数"] = int(is_yes(df_users["is_return"]).sum())
        if "has_new_demand" in df_users.columns:
            metrics["新需求工厂数"] = int(is_yes(df_users["has_new_demand"]).sum())
        elif "new_demand_summary" in df_users.columns:
            s = df_users["new_demand_summary"].fillna("").astype(str).str.strip()
            metrics["新需求工厂数"] = int((s != "").sum())
        if "has_issue" in df_users.columns:
            metrics["问题工厂数"] = int(is_yes(df_users["has_issue"]).sum())
        elif "issue_summary" in df_users.columns:
            s = df_users["issue_summary"].fillna("").astype(str).str.strip()
            metrics["问题工厂数"] = int((s != "").sum())
        if "upload_count" in df_users.columns:
            uc = pd.to_numeric(df_users["upload_count"], errors="coerce").fillna(0)
            metrics["周报上传图纸总数"] = int(uc.sum())
            metrics["周报上传图纸工厂数"] = int((uc > 0).sum())
        if "next_action" in df_users.columns:
            vc = df_users["next_action"].fillna("").astype(str).str.strip()
            vc = vc[vc != ""]
            for action, cnt in vc.value_counts().items():
                metrics[f"行动_{action}"] = int(cnt)

    return metrics


def intent_table(df_sessions: pd.DataFrame | None) -> pd.DataFrame:
    if df_sessions is None or df_sessions.empty:
        return pd.DataFrame()
    return q.high_freq_questions(df_sessions)


def next_action_table(df_users: pd.DataFrame | None) -> pd.DataFrame:
    if df_users is None or df_users.empty or "next_action" not in df_users.columns:
        return pd.DataFrame()
    s = df_users["next_action"].fillna("").astype(str).str.strip()
    s = s[s != ""]
    if s.empty:
        return pd.DataFrame()
    out = s.value_counts().rename_axis("建议动作").reset_index(name="工厂数")
    total = int(out["工厂数"].sum())
    out["占比"] = (out["工厂数"] / total * 100).round(2)
    return out


def issue_table(df_users: pd.DataFrame | None, top_n: int = 20) -> pd.DataFrame:
    if df_users is None or df_users.empty or "issue_summary" not in df_users.columns:
        return pd.DataFrame()
    d = df_users.copy()
    d["_issue"] = d["issue_summary"].fillna("").astype(str).str.strip()
    d = d[d["_issue"] != ""]
    if d.empty:
        return pd.DataFrame()
    cols = [c for c in ["user_id", "company_name", "level", "role", "next_action", "_issue"] if c in d.columns]
    out = d[cols].rename(columns={"_issue": "问题摘要"})
    return out.head(top_n).reset_index(drop=True)


def demand_table(df_users: pd.DataFrame | None, top_n: int = 20) -> pd.DataFrame:
    if df_users is None or df_users.empty or "new_demand_summary" not in df_users.columns:
        return pd.DataFrame()
    d = df_users.copy()
    d["_d"] = d["new_demand_summary"].fillna("").astype(str).str.strip()
    d = d[d["_d"] != ""]
    if d.empty:
        return pd.DataFrame()
    cols = [c for c in ["user_id", "company_name", "level", "role", "next_action", "_d"] if c in d.columns]
    return d[cols].rename(columns={"_d": "新需求摘要"}).head(top_n).reset_index(drop=True)


def scene_table(df_users: pd.DataFrame | None) -> pd.DataFrame:
    if df_users is None or df_users.empty or "scene" not in df_users.columns:
        return pd.DataFrame()
    out = df_users["scene"].fillna("未知").astype(str).value_counts().rename_axis("使用场景").reset_index(name="工厂数")
    total = int(out["工厂数"].sum())
    out["占比"] = (out["工厂数"] / total * 100).round(2)
    return out


def upload_type_table(df_sessions: pd.DataFrame | None, top_n: int = 15) -> pd.DataFrame:
    if df_sessions is None or df_sessions.empty or "upload_file_type" not in df_sessions.columns:
        return pd.DataFrame()
    d = df_sessions.loc[upload_mask(df_sessions), "upload_file_type"].astype(str).str.strip().str.lower()
    if d.empty:
        return pd.DataFrame()
    exploded = d.str.split(",").explode().str.strip()
    exploded = exploded[exploded.map(is_real_upload)]
    out = exploded.value_counts().rename_axis("文件类型").reset_index(name="次数")
    return out.head(top_n)


def _action_count(df_users: pd.DataFrame | None, keyword: str) -> int:
    if df_users is None or df_users.empty or "next_action" not in df_users.columns:
        return 0
    s = df_users["next_action"].fillna("").astype(str)
    return int(s.str.contains(keyword, na=False).sum())


def generate_local_conclusion(
    df_sessions: pd.DataFrame | None,
    df_users: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """不调用模型，基于本地指标生成可执行结论。"""
    metrics = collect_metrics(df_sessions, df_users)
    if not metrics:
        return {
            "结论": "尚未导入有效数据。",
            "数据证据": "",
            "影响": "",
            "原因判断": {"数据已支持": "", "待验证假设": ""},
            "下一步动作": [],
            "置信度": {"等级": "低", "理由": "无数据"},
            "来源": "本地规则",
        }

    factories = int(metrics.get("工厂数") or metrics.get("用户总表工厂数") or 0)
    questions_n = int(metrics.get("有效提问数") or 0)
    sessions_n = int(metrics.get("会话数") or 0)
    quote_pct = float(metrics.get("成本报价占比(%)") or 0)
    quote_n = int(metrics.get("成本报价提问数") or 0)
    other_pct = float(metrics.get("未归类占比(%)") or 0)
    other_n = int(metrics.get("未归类提问数") or 0)
    upload_n = int(metrics.get("上传图纸次数") or 0)
    upload_rate = float(metrics.get("提问附带图纸率(%)") or 0)
    issue_n = int(metrics.get("问题工厂数") or 0)
    demand_n = int(metrics.get("新需求工厂数") or 0)
    new_n = int(metrics.get("新用户数") or 0)
    return_n = int(metrics.get("回流用户数") or 0)
    d1 = metrics.get("D1留存率(%)")
    repeat_rate = metrics.get("重复提问率(%)")
    answer_rate = metrics.get("有回答率(%)")

    guide_n = _action_count(df_users, "新用户引导")
    revisit_n = _action_count(df_users, "回访")
    assess_n = _action_count(df_users, "产品评估")
    fix_n = _action_count(df_users, "排查")

    parts = [
        f"本周 {factories} 家工厂共 {sessions_n} 个会话、{questions_n} 条有效提问。",
    ]
    if quote_n:
        parts.append(f"问法归并后，成本报价 {quote_n} 条、占 {quote_pct}%。")
    if other_n:
        parts.append(f"仍有 {other_n} 条（{other_pct}%）未归入标准意图。")
    if upload_n:
        parts.append(f"真实上传图纸 {upload_n} 次，提问附带图纸率 {upload_rate}%。")
    if issue_n or demand_n:
        parts.append(f"用户总表标记问题工厂 {issue_n} 家、新需求 {demand_n} 家。")
    if new_n or return_n:
        parts.append(f"新用户 {new_n}、回流 {return_n}。")
    if d1 is not None:
        parts.append(f"会话口径 D1 留存 {d1}%。")

    evidence = []
    for k in (
        "工厂数", "会话数", "有效提问数", "成本报价提问数", "成本报价占比(%)",
        "未归类提问数", "未归类占比(%)", "上传图纸次数", "提问附带图纸率(%)",
        "问题工厂数", "新需求工厂数", "新用户数", "回流用户数", "D1留存率(%)",
        "重复提问率(%)", "有回答率(%)",
    ):
        if k in metrics:
            evidence.append(f"{k}={metrics[k]}")

    impact = []
    if quote_pct >= 40:
        impact.append("智能体主场景是核价报价，缺参追问和报价稳定性会直接拉高重复提问。")
    if issue_n:
        impact.append(f"{issue_n} 家工厂本周已被标为出现问题，其中高价值客户应优先人工跟进。")
    if new_n and guide_n:
        impact.append(f"{guide_n} 家被标「新用户引导」，二次使用做不起来会拉低周留存。")
    if not impact:
        impact.append("当前影响面主要落在问答质量和周报已标出的跟进名单。")

    supported = []
    if quote_n:
        supported.append(f"成本报价是第一意图（{quote_pct}%）。")
    if issue_n:
        supported.append(f"周报已给出 {issue_n} 家问题工厂及问题摘要。")
    if demand_n:
        supported.append(f"周报已给出 {demand_n} 条新需求摘要。")
    if upload_n:
        supported.append(f"图纸采用可按真实文件类型统计，不含「无」。")
    hypotheses = [
        "未归类长问法里有一部分是缺字段的报价需求，补追问模板可能下降「其他」占比。",
        "单周数据不能判断 D7/D30 和功能上线效果，需要第二周周报。",
    ]

    actions: list[dict[str, str]] = []
    if fix_n or issue_n:
        actions.append({
            "动作": f"本周优先回访「排查问题」{fix_n or issue_n} 家工厂，按高价值/高活跃分层排序",
            "优先级": "P0",
            "目标指标": "问题工厂数",
        })
    if quote_pct >= 30:
        actions.append({
            "动作": "围绕成本报价补齐材质/数量/工艺缺参追问，并收紧图纸预处理上下文不要塞进用户问法",
            "优先级": "P0",
            "目标指标": "成本报价占比(%)",
        })
    if assess_n or demand_n:
        actions.append({
            "动作": f"把 {demand_n or assess_n} 条新需求摘要进需求池，标是否做进下个版本",
            "优先级": "P1",
            "目标指标": "新需求工厂数",
        })
    if guide_n:
        actions.append({
            "动作": f"对 {guide_n} 家「新用户引导」工厂做二次使用触达（报价结果回访或图纸上传引导）",
            "优先级": "P1",
            "目标指标": "新用户数",
        })
    if other_pct >= 15:
        actions.append({
            "动作": "抽查未归类问法 Top 样本，补意图与同义表达后再观察未归类占比",
            "优先级": "P1",
            "目标指标": "未归类占比(%)",
        })
    if revisit_n:
        actions.append({
            "动作": f"回流/问题回访名单共 {revisit_n} 家，确认使用场景是否从询盘转到报价",
            "优先级": "P2",
            "目标指标": "回流用户数",
        })
    if not actions:
        actions.append({
            "动作": "保持周报观察，补第二周数据后看留存与环比",
            "优先级": "P2",
            "目标指标": "工厂数",
        })

    conf = "中"
    reason = "结论来自本周导出的客观统计和周报已有标签，未做跨周对比。"
    if factories >= 200 and questions_n >= 500:
        conf = "中高"
        reason = "单周样本足够看意图结构和跟进名单；留存与因果仍需多周数据。"

    extra = []
    if repeat_rate is not None:
        extra.append(f"重复提问率 {repeat_rate}%。")
    if answer_rate is not None:
        extra.append(f"有实质回答率 {answer_rate}%。")

    return {
        "结论": "".join(parts),
        "数据证据": "；".join(evidence),
        "影响": "".join(impact) + ("".join(extra)),
        "原因判断": {
            "数据已支持": "".join(supported),
            "待验证假设": "".join(hypotheses),
        },
        "下一步动作": actions,
        "置信度": {"等级": conf, "理由": reason},
        "来源": "本地规则",
        "指标": metrics,
    }
