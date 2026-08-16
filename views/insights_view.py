"""views/insights_view.py — AI 结论 / 报告编辑导出。"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from analysis import insights, questions as q
from core import config, storage


def _collect_metrics(df) -> dict:
    """收集本地客观指标（全部 pandas 计算）。"""
    metrics = {}
    if df is None or df.empty:
        return metrics
    metrics["事件总数"] = len(df)
    if "user_id" in df.columns:
        metrics["用户数"] = int(df["user_id"].nunique())
    if "session_id" in df.columns:
        metrics["会话数"] = int(df["session_id"].nunique())
    if "question_text" in df.columns:
        valid = df["question_text"].astype(str).str.strip().apply(q.is_valid_question)
        metrics["有效提问数"] = int(valid.sum())
    if "recognized_intent" in df.columns and "intent_confidence" in df.columns:
        conf = pd.to_numeric(df["intent_confidence"], errors="coerce")
        ok = (df["recognized_intent"].astype(str).str.strip().isin(["", "nan", "None", "null"]) == False) & (conf >= 0.6)  # noqa: E712
        total_q = int(df["question_text"].astype(str).str.strip().apply(q.is_valid_question).sum())
        metrics["识别成功率(%)"] = round(ok.sum() / total_q * 100, 2) if total_q else 0.0
    if "answer_status" in df.columns:
        valid_status = df["answer_status"].astype(str).str.strip().isin(config.VALID_ANSWER_STATUS)
        total_q = int(df["question_text"].astype(str).str.strip().apply(q.is_valid_question).sum()) if "question_text" in df.columns else len(df)
        metrics["有效回答率(%)"] = round(valid_status.sum() / total_q * 100, 2) if total_q else 0.0
    return metrics


def render():
    st.header("AI 结论与报告")
    df = st.session_state.df_sessions
    if df is None or df.empty:
        st.info("请先上传会话表")
        return

    metrics = _collect_metrics(df)
    if not metrics:
        st.info("无本地指标")
        return

    st.markdown("### 本地指标（AI 结论的证据来源）")
    st.json(metrics)

    if not config.has_api_key():
        st.warning("未配置 API Key，AI 结论不可用（本地指标已就绪）")
        return

    st.divider()
    st.markdown("### 生成 AI 结论")
    if st.button("生成结论", type="primary"):
        with st.spinner("生成中（含证据校验）..."):
            sample = []
            hf = q.high_freq_questions(df)
            if not hf.empty:
                sample = hf.head(10)["标准问题"].tolist()
            data, err = insights.generate_conclusion(metrics, sample)
            if err:
                st.error(err)
            else:
                st.session_state.conclusion = data
                st.success("结论已生成，证据校验通过")

    if st.session_state.get("conclusion"):
        data = st.session_state.conclusion
        st.markdown("### 结论详情")
        st.markdown(f"**结论**：{data.get('结论', '')}")
        st.markdown(f"**数据证据**：{data.get('数据证据', '')}")
        st.markdown(f"**影响**：{data.get('影响', '')}")
        rj = data.get("原因判断", {})
        st.markdown(f"**数据已支持**：{rj.get('数据已支持', '')}")
        st.markdown(f"**待验证假设**：{rj.get('待验证假设', '')}")
        st.markdown("**下一步动作**：")
        for a in data.get("下一步动作", []):
            st.markdown(f"- [{a.get('优先级', '')}] {a.get('动作', '')}（目标指标：{a.get('目标指标', '')}）")
        conf = data.get("置信度", {})
        st.markdown(f"**置信度**：{conf.get('等级', '')}（{conf.get('理由', '')}）")

        # 保存结论
        if st.button("保存结论"):
            storage.insert_insight(data)
            st.success("已保存")

        # 行动项沉淀
        if st.button("将下一步动作沉淀为行动项"):
            for a in data.get("下一步动作", []):
                storage.insert_action(
                    problem=a.get("动作", ""),
                    evidence=data.get("数据证据", ""),
                    priority=a.get("优先级", "P1"),
                    suggested_action=a.get("动作", ""),
                    target_metric=a.get("目标指标", ""),
                    review_time=None,
                )
            st.success("已沉淀到行动清单")

        # 生成报告
        st.divider()
        st.markdown("### 报告导出")
        if st.button("生成 Markdown 报告"):
            report = insights.build_markdown_report(
                summary=data.get("结论", ""),
                core_data=metrics,
                main_problems=[a.get("动作", "") for a in data.get("下一步动作", [])],
                cause_judgment=rj.get("数据已支持", "") + "；待验证：" + rj.get("待验证假设", ""),
                next_actions=data.get("下一步动作", []),
            )
            st.session_state.report_md = report

    if st.session_state.get("report_md"):
        st.markdown("### 报告初稿（可编辑）")
        edited = st.text_area("编辑报告", st.session_state.report_md, height=400)
        st.download_button(
            "导出 Markdown 报告",
            edited,
            "工厂智能体分析报告.md",
            "text/markdown",
        )
