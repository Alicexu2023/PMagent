"""views/actions_view.py — 行动清单 / 效果回看。"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from analysis import actions as act
from analysis import insights
from core import config, storage
from views.common import page_header


def render():
    page_header("行动清单", "待评估 → 处理中 → 待回看 → 已完成 / 已关闭")

    # 新建行动项
    with st.expander("新建行动项"):
        problem = st.text_input("问题")
        priority = st.selectbox("优先级", ["P0", "P1", "P2"])
        suggested_action = st.text_area("建议动作")
        evidence = st.text_input("证据")
        target_metric = st.text_input("目标指标")
        review_time = st.text_input("预计回看时间", placeholder="如 2026-09-01")
        if st.button("创建行动项"):
            if not problem:
                st.error("问题不能为空")
            else:
                act.create_action(problem, evidence, priority, suggested_action, target_metric, review_time)
                st.success("已创建")

    # 列表
    actions = storage.list_actions()
    if not actions:
        st.info("暂无行动项。可在「AI 结论与报告」把下一步动作沉淀进来，或手动创建。")
        return

    st.markdown("### 行动项列表")
    df = pd.DataFrame(actions)
    show_cols = ["id", "problem", "priority", "status", "target_metric", "review_time", "created_at"]
    st.dataframe(df[[c for c in show_cols if c in df.columns]])

    # 状态流转
    st.markdown("### 状态流转")
    sel_id = st.selectbox("选择行动项", actions, format_func=lambda x: f"#{x['id']} {x['problem'][:30]}")
    new_status = st.selectbox("目标状态", act.STATUS_FLOW)
    if st.button("更新状态"):
        ok, msg = act.transition(sel_id["id"], new_status)
        if ok:
            st.success("状态已更新")
        else:
            st.error(msg)

    # 效果回看
    st.divider()
    st.markdown("### 效果回看")
    if not config.has_api_key():
        st.warning("未配置 API Key，回看摘要不可用")
    else:
        review_id = st.selectbox("选择要回看的行动项", actions, key="review_sel", format_func=lambda x: f"#{x['id']} {x['problem'][:30]}")
        st.markdown("输入新数据下的同口径指标（用于与动作前快照对比）")
        new_metrics_text = st.text_area("新指标 JSON", placeholder='{"识别成功率(%)": 75.0, "有效回答率(%)": 80.0}')
        if st.button("生成回看摘要"):
            if not review_id.get("snapshot"):
                st.error("该行动项无动作前快照，无法对比")
            else:
                try:
                    new_metrics = json.loads(new_metrics_text)
                except Exception:
                    st.error("新指标 JSON 格式错误")
                    new_metrics = {}
                if new_metrics:
                    compare = act.review_action(review_id["id"], new_metrics)
                    if "error" in compare:
                        st.error(compare["error"])
                    else:
                        st.markdown("### 前后指标对比")
                        st.dataframe(pd.DataFrame(compare).T)
                        with st.spinner("AI 判定中..."):
                            data, err = insights.generate_review_summary(compare)
                            if err:
                                st.error(err)
                            else:
                                st.markdown(f"**判定**：{data.get('判定', '')}")
                                st.markdown(f"**摘要**：{data.get('摘要', '')}")
                                st.markdown(f"**理由**：{data.get('理由', '')}")
