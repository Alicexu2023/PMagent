"""views/import_view.py — 数据导入 / 字段映射 / 质检 / 首页概览。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from analysis import ingestion
from analysis import questions as q
from core import storage


def _save_upload(uploaded_file) -> Path:
    """保存上传文件到 data/uploads/。"""
    from core.config import UPLOAD_DIR
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / uploaded_file.name
    with open(dest, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest


def _show_report(rep: ingestion.QualityReport, table_label: str):
    """展示质量报告。"""
    d = rep.to_dict()
    st.markdown(f"### {table_label} 质量报告")
    c1, c2, c3 = st.columns(3)
    c1.metric("原始记录数", d["raw_count"])
    c2.metric("有效记录数", d["valid_count"])
    c3.metric("排除记录数", d["excluded_count"])

    if d["exclude_reasons"]:
        st.markdown("**排除原因**")
        for reason, cnt in d["exclude_reasons"].items():
            st.write(f"- {reason}: {cnt} 条")

    if d["missing_required"]:
        st.error("缺少必需字段：" + ", ".join(d["missing_required"]) + "，导入被阻断")

    # 可做/不可做分析
    st.markdown("**可做分析**")
    if d["available_analyses"]:
        st.write("、".join(d["available_analyses"]))
    else:
        st.write("无")
    if d["unavailable_analyses"]:
        st.markdown("**不可做分析（缺字段）**")
        for name, missing in d["unavailable_analyses"].items():
            st.warning(f"- {name}：缺少 {', '.join(missing)}")


def render():
    st.header("数据导入与质量门禁")
    st.caption("上传数据表（支持多周，用户总表/会话表可一次传多份）：用户总表、会话表、反馈 XLSX（反馈表为空不阻塞）")

    c1, c2 = st.columns(2)
    with c1:
        f_users = st.file_uploader("用户总表（可多选，每周一份）", type=["csv", "xlsx"], accept_multiple_files=True, key="fu")
    with c2:
        f_sessions = st.file_uploader("会话表（可多选，每周一份）", type=["csv"], accept_multiple_files=True, key="fs")
    f_feedback = st.file_uploader("反馈表 XLSX（可选）", type=["xlsx"], key="ff")

    if st.button("开始导入并质检", type="primary"):
        ok = False
        # 用户总表（多周）
        if f_users:
            history = list(st.session_state.get("df_users_history", []))
            for fu in f_users:
                p = _save_upload(fu)
                df, rep = ingestion.ingest(p, "users", fu.name)
                history.append({"df": df, "rep": rep, "week": rep.week_label, "file": fu.name})
                _show_report(rep, f"用户总表 {fu.name}")
            # 按周次排序
            history.sort(key=lambda x: x["week"] or "")
            st.session_state.df_users_history = history
            st.session_state.df_users = history[-1]["df"] if history else None
            ok = True
        else:
            st.info("未上传用户总表")

        # 会话表（多周）
        if f_sessions:
            shistory = list(st.session_state.get("df_sessions_history", []))
            for fs_ in f_sessions:
                p = _save_upload(fs_)
                df, rep = ingestion.ingest(p, "sessions", fs_.name)
                shistory.append({"df": df, "rep": rep, "week": rep.week_label, "file": fs_.name})
                _show_report(rep, f"会话表 {fs_.name}")
            shistory.sort(key=lambda x: x["week"] or "")
            st.session_state.df_sessions_history = shistory
            st.session_state.df_sessions = shistory[-1]["df"] if shistory else None
            ok = True
        else:
            st.info("未上传会话表")

        # 反馈表
        if f_feedback is not None:
            p = _save_upload(f_feedback)
            df, rep = ingestion.ingest(p, "feedback", f_feedback.name)
            st.session_state.df_feedback = df
            st.session_state.reports["feedback"] = rep
            _show_report(rep, "反馈表")
            ok = True

        # 关联差异（用户表 vs 会话表 的 user_id 差集）
        if st.session_state.df_users is not None and st.session_state.df_sessions is not None:
            u_users = set(st.session_state.df_users["user_id"].astype(str))
            s_users = set(st.session_state.df_sessions["user_id"].astype(str))
            diff = u_users ^ s_users
            st.markdown(f"**关联差异**：用户总表与会话表 user_id 相差 {len(diff)} 个")

        if ok:
            st.success("导入完成")

    # 历史批次
    st.divider()
    st.markdown("### 历史批次")
    batches = storage.list_batches()
    if batches:
        st.dataframe(pd.DataFrame(batches)[["id", "week_label", "file_name", "table_type", "row_count", "valid_count", "excluded_count", "created_at"]])
    else:
        st.info("暂无历史批次")


def render_overview():
    """首页概览：结论摘要。"""
    st.header("首页概览")
    if st.session_state.df_sessions is None and st.session_state.df_users is None:
        st.info("请先在「导入与质检」上传数据")
        return

    # 多周留存与环比（优先展示）
    u_history = st.session_state.get("df_users_history", [])
    if len(u_history) >= 2:
        st.markdown("### 多周留存与环比")
        from analysis import retention
        prev = u_history[-2]["df"]
        curr = u_history[-1]["df"]
        prev_week = u_history[-2]["week"]
        curr_week = u_history[-1]["week"]
        st.caption(f"对比周期：{prev_week or '上周'} → {curr_week or '本周'}")

        wr = retention.weekly_retention(prev, curr)
        if wr:
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("上周活跃工厂", wr["上周活跃数"])
            c2.metric("本周活跃工厂", wr["本周活跃数"])
            c3.metric("留存工厂", wr["留存数"])
            c4.metric("流失工厂", wr["流失数"])
            c5.metric("新增工厂", wr["新增数"])
            c6.metric("周留存率(%)", wr["周留存率(%)"])

        wow = retention.week_over_week(prev, curr)
        if not wow.empty:
            st.markdown("**环比指标**")
            st.dataframe(wow)
        st.divider()
    elif st.session_state.get("df_users") is not None:
        st.caption("当前仅单周数据，上传第二周后可查看工厂周留存与环比")

    df = st.session_state.df_sessions
    if df is not None and not df.empty:
        st.markdown("### 核心指标")
        c1, c2, c3, c4 = st.columns(4)
        total_rows = len(df)
        users = df["user_id"].nunique() if "user_id" in df.columns else 0
        sessions = df["session_id"].nunique() if "session_id" in df.columns else 0
        questions = 0
        if "question_text" in df.columns:
            questions = int((df["question_text"].notna() & df["question_text"].astype(str).str.strip().apply(q.is_valid_question)).sum())
        c1.metric("事件总数", total_rows)
        c2.metric("工厂数(用户)", users)
        c3.metric("会话数", sessions)
        c4.metric("有效提问数", questions)

        # 周次识别
        week = ingestion.detect_week_label(df)
        st.caption(f"识别周次：{week or '无法识别'}")
        if week:
            st.warning("当前为单周数据，留存与环比需至少两周数据")

        # 上传图纸采用（会话表 upload_file_type）
        if "upload_file_type" in df.columns:
            st.markdown("### 上传图纸采用")
            ut = df["upload_file_type"].notna()
            upload_cnt = int(ut.sum())
            upload_users = df.loc[ut, "user_id"].nunique() if "user_id" in df.columns else 0
            c1, c2 = st.columns(2)
            c1.metric("上传图纸次数", upload_cnt)
            c2.metric("上传图纸工厂数", upload_users)
            # 文件类型分布
            type_dist = df.loc[ut, "upload_file_type"].astype(str).str.strip().str.lower().value_counts()
            if not type_dist.empty:
                st.dataframe(pd.DataFrame(type_dist).rename(columns={type_dist.name or 0: "次数"}).head(10))

        # 高频问题摘要
        st.markdown("### 高频问题 Top 10")
        hf = q.high_freq_questions(df)
        if not hf.empty:
            st.dataframe(hf.head(10)[["标准问题", "提问次数", "提问人数", "占比"]])
        else:
            st.info("暂无高频问题数据")

    # 用户总表：分群与上传图纸
    dfu = st.session_state.df_users
    if dfu is not None and not dfu.empty:
        st.markdown("### 用户分群")
        group_cols = [c for c in ["role", "member_type", "level", "region", "process_type"] if c in dfu.columns]
        if group_cols:
            sel_group = st.selectbox("分群维度", group_cols)
            dist = dfu[sel_group].astype(str).value_counts()
            st.dataframe(pd.DataFrame(dist).rename(columns={sel_group: "数量"}).head(20))
        else:
            st.info("无角色/会员/分层/地区等分群字段")

        # 上传图纸采用（用户总表汇总）
        if "upload_count" in dfu.columns:
            st.markdown("### 上传图纸汇总（用户总表）")
            uc = pd.to_numeric(dfu["upload_count"], errors="coerce").fillna(0).astype(int)
            c1, c2, c3 = st.columns(3)
            c1.metric("上传图纸工厂数", int((uc > 0).sum()))
            c2.metric("上传图纸总数", int(uc.sum()))
            c3.metric("人均上传数", round(uc.mean(), 2))

    # 反馈表摘要
    if st.session_state.df_feedback is not None and not st.session_state.df_feedback.empty:
        st.markdown("### 反馈表")
        st.dataframe(st.session_state.df_feedback.head(20))
