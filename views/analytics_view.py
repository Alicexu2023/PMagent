"""views/analytics_view.py — 漏斗分析 / 留存分析 / 属性筛选。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis import funnel, retention, questions as q


def _get_df():
    return st.session_state.df_sessions


def render_funnel():
    st.header("漏斗分析")
    df = _get_df()
    if df is None or df.empty:
        st.info("请先上传会话表")
        return

    if "business_result" not in df.columns:
        st.warning("缺少 business_result 字段，业务转化/漏斗最后一步可能不完整")

    st.markdown("### 默认链路")
    f = funnel.funnel_analysis(df)
    if f.empty:
        st.info("无法计算漏斗")
        return
    st.dataframe(f)

    # 漏斗图
    import plotly.graph_objects as go
    fig = go.Figure(go.Funnel(
        y=f["步骤"], x=f["达标用户数"],
        textinfo="value+percent previous",
    ))
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

    # 最大流失步骤
    if len(f) > 1:
        churn = f.iloc[1:]
        max_churn_idx = churn["流失率(%)"].idxmax()
        st.markdown(f"**最大流失步骤**：{f.loc[max_churn_idx, '步骤']}（流失率 {f.loc[max_churn_idx, '流失率(%)']}%）")

    # 下钻
    st.markdown("### 流失下钻")
    step_names = f["步骤"].tolist()
    sel_step = st.selectbox("选择步骤下钻", step_names)
    by = st.selectbox("下钻维度", ["recognized_intent", "event_name"], key="funnel_by")
    drill = funnel.funnel_drilldown(df, sel_step, by=by)
    if not drill.empty:
        st.dataframe(drill.head(20))
    else:
        st.info("无下钻数据")


def render_retention():
    st.header("留存分析")
    df = _get_df()
    if df is None or df.empty:
        st.info("请先上传会话表")
        return

    if "user_id" not in df.columns or "event_time" not in df.columns:
        st.error("缺少 user_id 或 event_time，无法计算留存")
        return

    st.markdown("### D1/D7/D30 留存")
    r, note = retention.retention_analysis(df)
    if r.empty:
        st.info(note or "无法计算留存")
        return
    st.dataframe(r)
    if note:
        st.warning(note)

    # 新老用户对比
    st.markdown("### 对比维度")
    if "user_properties" in df.columns or "role" in df.columns or "member_level" in df.columns:
        group_col = st.selectbox("对比维度", ["recognized_intent"] + [c for c in df.columns if c in ("role", "member_level", "scene", "user_properties", "factory", "region")], key="ret_group")
        groups = retention.retention_by_group(df, group_col)
        if groups:
            for gname, grp_df in groups.items():
                st.markdown(f"**{gname}**")
                st.dataframe(grp_df)
        else:
            st.info("该维度无数据或样本不足")
    else:
        st.info("无角色/分层/场景等属性字段，仅支持按首次问题类型对比（recognized_intent）")
