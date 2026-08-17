"""views/insights_view.py — 本地结论 / 模型润色 / 报告导出。"""
from __future__ import annotations

import streamlit as st

from analysis import insights, product
from analysis import questions as q
from core import config, storage
from views.common import page_header, show_conclusion


def render():
    page_header("结论与报告", "本地结论导入后自动生成。有 Key 时可用模型润色。")
    df = st.session_state.df_sessions
    dfu = st.session_state.df_users
    if (df is None or df.empty) and (dfu is None or dfu.empty):
        st.info("请先上传会话表或用户总表")
        return

    local = insights.generate_local_conclusion(df, dfu)
    st.session_state.setdefault("conclusion", local)

    st.markdown("### 本地结论（导入后自动生成，不依赖模型）")
    show_conclusion(local)

    metrics = product.collect_metrics(df, dfu)
    with st.expander("本地指标明细"):
        st.json(metrics)

    if config.has_api_key():
        st.divider()
        st.markdown("### 用模型润色结论")
        if st.button("生成模型结论", type="primary"):
            with st.spinner("生成中..."):
                sample = []
                if df is not None:
                    exact = q.exact_questions(df, top_n=15)
                    if not exact.empty:
                        sample = exact["问法"].tolist()
                    companies = []
                    if "company_name" in df.columns:
                        companies = df["company_name"].dropna().astype(str).unique().tolist()[:80]
                    from analysis import ai_client
                    sample = ai_client.desensitize_sample(sample, 15, extra_terms=companies)
                extra = local.get("结论", "")
                data, err = insights.generate_conclusion(metrics, sample, extra_context=extra)
                if err:
                    st.error(err)
                else:
                    st.session_state.conclusion = data
                    st.success("模型结论已生成")
                    if data.get("证据警告"):
                        st.warning(data["证据警告"])

    data = st.session_state.get("conclusion") or local
    if data and data.get("来源") == "模型":
        st.markdown("### 模型结论")
        show_conclusion(data)

    if data:
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("保存当前结论"):
                storage.insert_insight(data)
                st.success("已保存")
        with c2:
            if st.button("沉淀为行动项"):
                for a in data.get("下一步动作", []):
                    storage.insert_action(
                        problem=a.get("动作", ""),
                        evidence=data.get("数据证据", ""),
                        priority=a.get("优先级", "P1"),
                        suggested_action=a.get("动作", ""),
                        target_metric=a.get("目标指标", ""),
                        review_time=None,
                        snapshot=metrics,
                    )
                st.success("已沉淀到行动清单")
        with c3:
            if st.button("生成 Markdown 报告"):
                rj = data.get("原因判断") or {}
                st.session_state.report_md = insights.build_markdown_report(
                    summary=data.get("结论", ""),
                    core_data=metrics,
                    main_problems=[a.get("动作", "") for a in data.get("下一步动作", [])],
                    cause_judgment=(rj.get("数据已支持", "") or "") + "；待验证：" + (rj.get("待验证假设", "") or ""),
                    next_actions=data.get("下一步动作", []),
                )

    if st.session_state.get("report_md"):
        st.markdown("### 报告初稿（可编辑）")
        edited = st.text_area("编辑报告", st.session_state.report_md, height=400)
        st.download_button("导出 Markdown 报告", edited, "工厂智能体分析报告.md", "text/markdown")
