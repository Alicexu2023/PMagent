"""views/analytics_view.py — 漏斗分析 / 留存分析。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis import funnel, retention
from views.common import page_header


def _get_df():
    return st.session_state.df_sessions


def render_funnel():
    page_header("漏斗分析", "没有埋点时按提问 → 回答 → 图纸计算。")
    df = _get_df()
    dfu = st.session_state.df_users
    if (df is None or df.empty) and (dfu is None or dfu.empty):
        st.info("请先上传会话表")
        return

    if df is not None and "event_name" in df.columns:
        st.caption("检测到 event_name，按埋点行为漏斗计算。")
        f = funnel.funnel_analysis(df)
    elif df is not None and not df.empty:
        st.caption("会话表没有埋点事件。按问答链路计算：留下记录 → 有效提问 → 实质回答 → 上传真实图纸。")
        f = funnel.qa_funnel(df)
    else:
        f = pd.DataFrame()

    if f.empty:
        st.info("无法计算漏斗")
        return

    st.markdown("### 漏斗步骤")
    st.dataframe(f)

    import plotly.graph_objects as go
    fig = go.Figure(go.Funnel(
        y=f["步骤"], x=f["达标用户数"],
        textinfo="value+percent previous",
    ))
    fig.update_layout(height=400)
    st.plotly_chart(fig, width="stretch")

    if len(f) > 1:
        churn = f.iloc[1:]
        max_churn_idx = churn["流失率(%)"].idxmax()
        st.markdown(
            f"**最大流失步骤**：{f.loc[max_churn_idx, '步骤']}"
            f"（流失率 {f.loc[max_churn_idx, '流失率(%)']}%）"
        )

    st.markdown("### 下钻")
    step_names = f["步骤"].tolist()
    sel_step = st.selectbox("选择步骤下钻", step_names)
    drill_opts = [c for c in ["_std", "role", "process_type", "recognized_intent", "event_name"] if c == "_std" or (df is not None and c in df.columns)]
    if not drill_opts:
        drill_opts = ["role"]
    by = st.selectbox("下钻维度", drill_opts, key="funnel_by")
    if df is not None:
        drill = funnel.funnel_drilldown(df, sel_step, by=by)
        if not drill.empty:
            st.dataframe(drill.head(20))
        else:
            st.info("无下钻数据")


def render_retention():
    page_header("留存分析", "单周只能看 D1。再传一周用户总表可看工厂周留存。")
    df = _get_df()
    dfu = st.session_state.df_users
    if (df is None or df.empty) and (dfu is None or dfu.empty):
        st.info("请先上传会话表或用户总表")
        return

    if df is not None and not df.empty and "user_id" in df.columns and "event_time" in df.columns:
        st.markdown("### D1/D7/D30 留存（会话提问口径）")
        r, note = retention.retention_analysis(df)
        if r.empty:
            st.info(note or "无法计算留存")
        else:
            st.dataframe(r)
            if note:
                st.warning(note)

        st.markdown("### 对比维度")
        group_cols = [
            c for c in ["role", "process_type", "scene", "level", "member_type", "region", "recognized_intent"]
            if c in df.columns
        ]
        if group_cols:
            group_col = st.selectbox("对比维度", group_cols, key="ret_group")
            groups = retention.retention_by_group(df, group_col)
            if groups:
                # 分组太多时只展示前几个
                shown = 0
                for gname, grp_df in groups.items():
                    st.markdown(f"**{gname}**")
                    st.dataframe(grp_df)
                    shown += 1
                    if shown >= 8:
                        st.caption("仅展示前 8 个分组")
                        break
            else:
                st.info("该维度无数据或样本不足")
        else:
            st.info("会话表无角色/工艺等分群字段")
    else:
        st.info("会话表缺少 user_id 或 event_time，无法按日留存")

    u_history = st.session_state.get("df_users_history") or []
    if len(u_history) >= 2:
        st.markdown("### 工厂周留存（用户总表）")
        prev = u_history[-2]["df"]
        curr = u_history[-1]["df"]
        wr = retention.weekly_retention(prev, curr)
        if wr:
            st.json(wr)
        wow = retention.week_over_week(prev, curr)
        if not wow.empty:
            st.dataframe(wow)
    elif dfu is not None:
        st.caption("再上传一周用户总表后，可看工厂周留存与环比")
