"""views/paths.py — 路径分析：埋点路径或会话问法序列。"""
from __future__ import annotations

import streamlit as st

from analysis import ai_client, paths
from core import config


def render():
    st.header("路径分析")
    df = st.session_state.df_sessions
    if df is None or df.empty:
        st.info("请先上传会话表")
        return

    if "page_name" not in df.columns and "event_name" not in df.columns:
        st.caption("没有页面/事件埋点。按同一会话里的提问意图序列看前后步。")
    elif "page_name" not in df.columns:
        st.caption("缺少 page_name，若识别不到提问事件会回退到问法序列。")

    before = st.slider("提问前步数", 1, 10, 5)
    after = st.slider("提问后步数", 1, 10, 5)

    st.markdown("### 噪声事件排除")
    extra_noise = st.text_input("额外噪声关键词（逗号分隔）", placeholder="例如：曝光,心跳")
    noise_list = [x.strip() for x in extra_noise.split(",") if x.strip()] if extra_noise else None

    paths_df = paths.build_paths(df, before=before, after=after, exclude_noise=noise_list)
    if paths_df.empty:
        st.info("无法构建路径")
        return

    users_n = paths_df["user_id"].nunique() if "user_id" in paths_df.columns else 0
    sess_n = paths_df["session_id"].nunique() if "session_id" in paths_df.columns else 0
    st.markdown(f"### Top 路径（{users_n} 工厂 / {sess_n} 会话）")
    top = paths.top_paths(paths_df)
    if not top.empty:
        st.dataframe(top)
    else:
        st.info("无路径数据")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 提问前来源 Top")
        b = paths.path_before_top(paths_df)
        if not b.empty:
            st.dataframe(b)
    with c2:
        st.markdown("### 提问后去向 Top")
        a = paths.path_after_top(paths_df)
        if not a.empty:
            st.dataframe(a)

    st.divider()
    st.markdown("### AI 路径解读")
    if not config.has_api_key():
        st.info("未配置 API Key：上方路径统计仍可用。")
        return

    if st.button("生成路径解读"):
        top_paths_str = ""
        if not top.empty:
            top_paths_str = "\n".join(
                f"- {row['full_path']}（频次 {row['频次']}，用户 {row['用户数']}）"
                for _, row in top.head(10).iterrows()
            )
        system = (
            "你是工厂智能体路径分析助手。请描述主要路径和异常路径。\n"
            "严格禁止因果表述（如'导致''造成'），只用'较多用户经过/在此离开'等描述性表达。\n"
            "只用 JSON 输出：{\"解读\":\"...\",\"主要路径\":\"...\",\"异常路径\":\"...\"}"
        )
        content, err = ai_client.chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": f"Top 路径：\n{top_paths_str}"}],
            json_mode=True,
        )
        if err:
            st.error(err)
        else:
            data, perr = ai_client.parse_json_response(content)
            if perr:
                st.error(perr)
            else:
                st.markdown(f"**解读**：{data.get('解读', '')}")
                st.markdown(f"**主要路径**：{data.get('主要路径', '')}")
                st.markdown(f"**异常路径**：{data.get('异常路径', '')}")
