"""views/questions_view.py — 问答分析：高频问题 / 真实问法 / AI 归并 / 同义表达。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from analysis import questions as q
from analysis import insights
from core import config, storage


def render():
    st.header("问答分析")
    df = st.session_state.df_sessions
    if df is None or df.empty:
        st.info("请先在「导入与质检」上传会话表")
        return

    # 高频问题
    hf = q.high_freq_questions(df)
    if hf.empty:
        st.info("暂无有效提问数据")
        return

    st.markdown("### 高频标准问题")
    st.dataframe(hf[["标准问题", "提问次数", "提问人数", "占比"]])

    # 选择具体问题查看真实问法
    st.markdown("### 真实问法明细")
    options = hf["标准问题"].tolist()
    selected = st.selectbox("选择标准问题", options)

    top_n = st.slider("展示真实问法条数", 5, 20, 20)
    real = q.real_questions(df, selected, top_n=top_n)
    if real:
        st.dataframe(pd.DataFrame(real))
    else:
        st.info("该问题下无真实问法")

    # 时间趋势
    st.markdown("### 时间趋势")
    trend_freq = st.radio("趋势粒度", ["日", "周"], horizontal=True, key="trend_freq")
    freq = "D" if trend_freq == "日" else "W"
    trend = q.question_trend(df, selected, freq=freq)
    if not trend.empty:
        st.line_chart(trend.set_index("时间"))
    else:
        st.info("无趋势数据")

    # 会话内重复提问
    st.markdown("### 会话内重复提问")
    rep_cnt, valid_cnt, rep_df = q.repeat_questions(df)
    if valid_cnt > 0:
        rate = round(rep_cnt / valid_cnt * 100, 2)
        c1, c2, c3 = st.columns(3)
        c1.metric("重复提问数", rep_cnt)
        c2.metric("有效提问数", valid_cnt)
        c3.metric("重复提问率(%)", rate)
    else:
        st.info("无法计算重复提问（缺 session_id 或时间字段）")

    # AI 归并与同义表达
    st.divider()
    st.markdown("### AI 归并与同义表达")
    if not config.has_api_key():
        st.warning("未配置 API Key，AI 归并不可用（本地高频统计不受影响）")
        return

    sample_texts = hf.head(20)["标准问题"].tolist()
    if st.button("AI 归并问法", type="primary"):
        with st.spinner("AI 归并中..."):
            data, err = insights.generate_cluster(sample_texts)
            if err:
                st.error(err)
            else:
                st.session_state.cluster_result = data
                stds = data.get("标准问题", [])
                st.success(f"归并出 {len(stds)} 个标准问题")
                for s in stds:
                    st.markdown(f"**{s.get('标准问题名称', '')}**")
                    st.write("包含问法：" + "、".join(s.get("包含问法", [])[:10]))
                    st.caption(f"建议意图：{s.get('建议意图', '')}；理由：{s.get('理由', '')}")

    # 同义表达生成
    st.markdown("### 同义表达建议")
    sel_std = st.selectbox("为目标标准问题生成同义表达", options, key="syn_sel")
    if st.button("生成同义表达"):
        with st.spinner("生成中..."):
            # 取该标准问题的真实问法作为样本
            sample = [r["问法"] for r in q.real_questions(df, sel_std, top_n=20)]
            syns, err = insights.generate_synonyms(sel_std, sample)
            if err:
                st.error(err)
            else:
                st.session_state.synonyms = syns
                st.success(f"生成 {len(syns)} 条同义表达")
                st.dataframe(pd.DataFrame(syns))

    # 保存同义表达到 SQLite + 导出 CSV
    if st.session_state.get("synonyms"):
        if st.button("保存同义表达到清单"):
            for s in st.session_state.synonyms:
                storage.upsert_synonym(
                    raw_text=s.get("原始问法", ""),
                    std_question=s.get("建议标准问题", ""),
                    intent=s.get("建议意图", ""),
                    reason=s.get("建议理由", ""),
                    freq=0,
                    affected_users=0,
                )
            st.success("已保存")

        csv_text = insights.export_synonyms_csv(st.session_state.synonyms)
        st.download_button("导出同义表达 CSV", csv_text, "同义表达.csv", "text/csv")

    # 已保存的同义表达（可人工修改）
    st.markdown("### 已保存同义表达（可人工修改）")
    saved = storage.list_synonyms()
    if saved:
        df_saved = pd.DataFrame(saved)
        st.dataframe(df_saved[["id", "raw_text", "std_question", "intent", "reason", "freq", "edited"]])
    else:
        st.info("暂无已保存的同义表达")
