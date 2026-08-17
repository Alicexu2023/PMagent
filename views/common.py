"""views/common.py — 页面共用展示。"""
from __future__ import annotations

import streamlit as st


def show_conclusion(data: dict):
    if not data:
        return
    src = data.get("来源") or "本地规则"
    st.caption(f"结论来源：{src}")
    st.markdown(f"**结论**：{data.get('结论', '')}")
    if data.get("数据证据"):
        st.markdown(f"**数据证据**：{data.get('数据证据', '')}")
    if data.get("影响"):
        st.markdown(f"**影响**：{data.get('影响', '')}")
    rj = data.get("原因判断") or {}
    if isinstance(rj, dict):
        if rj.get("数据已支持"):
            st.markdown(f"**数据已支持**：{rj.get('数据已支持')}")
        if rj.get("待验证假设"):
            st.markdown(f"**待验证假设**：{rj.get('待验证假设')}")
    st.markdown("**下一步动作**：")
    for a in data.get("下一步动作") or []:
        st.markdown(f"- [{a.get('优先级', '')}] {a.get('动作', '')}（目标指标：{a.get('目标指标', '')}）")
    conf = data.get("置信度") or {}
    if conf:
        st.markdown(f"**置信度**：{conf.get('等级', '')}（{conf.get('理由', '')}）")
    if data.get("证据警告"):
        st.warning(data["证据警告"])
