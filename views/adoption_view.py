"""views/adoption_view.py — 功能采用 / 图纸类型 / 使用场景。"""
from __future__ import annotations

import streamlit as st

from analysis import adoption, product
from views.common import page_header


def render():
    page_header("功能采用", "没有功能埋点时，按图纸类型和使用场景看采用。")
    df = st.session_state.df_sessions
    dfu = st.session_state.df_users
    if (df is None or df.empty) and (dfu is None or dfu.empty):
        st.info("请先上传会话表或用户总表")
        return

    if df is not None and not df.empty:
        if "feature_name" in df.columns:
            st.markdown("### 功能采用指标")
            a = adoption.adoption_analysis(df)
        else:
            st.caption("没有 feature_name。按上传图纸类型看采用（已排除「无」）。")
            st.markdown("### 图纸类型采用")
            a = adoption.upload_type_adoption(df)
        if a.empty:
            st.info("无采用数据")
        else:
            st.dataframe(a)
            st.markdown("### 上线前后对比")
            features = a["功能"].tolist()
            sel_feat = st.selectbox("选择类型/功能", features)
            launch_date = st.date_input("功能上线日期")
            if st.button("对比上线前后"):
                if "feature_name" in df.columns:
                    cmp_df, note = adoption.adoption_before_after(
                        df, sel_feat, launch_date.strftime("%Y-%m-%d")
                    )
                else:
                    tmp = df.copy()
                    tmp["feature_name"] = tmp.get("upload_file_type", "").astype(str).str.strip().str.lower()
                    cmp_df, note = adoption.adoption_before_after(
                        tmp, sel_feat, launch_date.strftime("%Y-%m-%d")
                    )
                if cmp_df.empty:
                    st.info(note or "无对比数据")
                else:
                    st.dataframe(cmp_df)
                    if note:
                        st.warning(note)

    scenes = product.scene_table(dfu)
    if not scenes.empty:
        st.markdown("### 本周主要使用场景（用户总表）")
        st.dataframe(scenes)
