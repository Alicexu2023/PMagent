"""views/adoption_view.py — 功能采用分析。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis import adoption


def render():
    st.header("功能采用分析")
    df = st.session_state.df_sessions
    if df is None or df.empty:
        st.info("请先上传会话表")
        return

    if "feature_name" not in df.columns:
        st.error("缺少 feature_name 字段，功能采用分析不可用")
        return

    st.markdown("### 功能采用指标")
    a = adoption.adoption_analysis(df)
    if a.empty:
        st.info("无功能采用数据")
        return
    st.dataframe(a)

    # 上线前后对比
    st.markdown("### 功能上线前后对比")
    features = a["功能"].tolist()
    sel_feat = st.selectbox("选择功能", features)
    launch_date = st.date_input("功能上线日期")
    if st.button("对比上线前后"):
        cmp_df, note = adoption.adoption_before_after(
            df, sel_feat, launch_date.strftime("%Y-%m-%d")
        )
        if cmp_df.empty:
            st.info(note or "无对比数据")
        else:
            st.dataframe(cmp_df)
            if note:
                st.warning(note)
