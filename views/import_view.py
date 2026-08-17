"""views/import_view.py — 数据导入 / 字段映射 / 质检 / 首页概览。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from analysis import ingestion, insights, product, retention
from analysis import questions as q
from core import storage
from views.common import page_header, show_conclusion


def _save_upload(uploaded_file) -> Path:
    """保存上传文件到 uploads/。"""
    from core.config import UPLOAD_DIR
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / uploaded_file.name
    with open(dest, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest


def _upsert_history(history: list, item: dict) -> list:
    history = [h for h in history if h.get("file") != item.get("file")]
    history.append(item)
    history.sort(key=lambda x: x.get("week") or "")
    return history


def _upload_sig(files) -> tuple:
    if not files:
        return ()
    if not isinstance(files, (list, tuple)):
        files = [files]
    return tuple((getattr(f, "name", ""), getattr(f, "size", 0)) for f in files)


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

    st.markdown("**可做分析**")
    if d["available_analyses"]:
        st.write("、".join(d["available_analyses"]))
    else:
        st.write("无")
    if d["unavailable_analyses"]:
        st.markdown("**不可做 / 已改用替代口径**")
        for name, missing in d["unavailable_analyses"].items():
            st.caption(f"- {name}：{', '.join(missing)}")


def _ingest_files(f_users, f_sessions, f_feedback, show_reports: bool = True) -> bool:
    ok = False
    if f_users:
        history = list(st.session_state.get("df_users_history") or [])
        for fu in f_users:
            p = _save_upload(fu)
            df, rep = ingestion.ingest(p, "users", fu.name)
            history = _upsert_history(history, {"df": df, "rep": rep, "week": rep.week_label, "file": fu.name})
            if show_reports:
                _show_report(rep, f"用户总表 {fu.name}")
        st.session_state.df_users_history = history
        st.session_state.df_users = history[-1]["df"] if history else None
        ok = True

    if f_sessions:
        shistory = list(st.session_state.get("df_sessions_history") or [])
        for fs_ in f_sessions:
            p = _save_upload(fs_)
            df, rep = ingestion.ingest(p, "sessions", fs_.name)
            shistory = _upsert_history(shistory, {"df": df, "rep": rep, "week": rep.week_label, "file": fs_.name})
            if show_reports:
                _show_report(rep, f"会话表 {fs_.name}")
        st.session_state.df_sessions_history = shistory
        st.session_state.df_sessions = shistory[-1]["df"] if shistory else None
        ok = True

    if f_feedback is not None:
        p = _save_upload(f_feedback)
        df, rep = ingestion.ingest(p, "feedback", f_feedback.name)
        st.session_state.df_feedback = df
        st.session_state.reports["feedback"] = rep
        if show_reports:
            _show_report(rep, "反馈表")
        ok = True

    if ok:
        st.session_state.conclusion = insights.generate_local_conclusion(
            st.session_state.df_sessions,
            st.session_state.df_users,
        )
    return ok


def render():
    page_header("数据导入", "选完文件会自动质检。不必等 API Key。也可把样表放进 lists/ 后重启。")

    c1, c2 = st.columns(2)
    with c1:
        f_users = st.file_uploader(
            "用户总表（可多选，每周一份）", type=["csv", "xlsx"], accept_multiple_files=True, key="fu",
        )
    with c2:
        f_sessions = st.file_uploader(
            "会话表（可多选，每周一份）", type=["csv"], accept_multiple_files=True, key="fs",
        )
    f_feedback = st.file_uploader("反馈表 XLSX（可选）", type=["xlsx"], key="ff")

    sig = (_upload_sig(f_users), _upload_sig(f_sessions), _upload_sig(f_feedback))
    auto_clicked = False
    if any(sig) and sig != st.session_state.get("_upload_sig"):
        auto_clicked = True
        st.session_state._upload_sig = sig
        ok = _ingest_files(f_users, f_sessions, f_feedback, show_reports=True)
        if ok:
            st.success("已自动导入并完成本地分析，请看「首页概览」")

    if st.button("重新导入并质检", type="primary"):
        if not f_users and not f_sessions and f_feedback is None:
            st.info("请先选择要上传的文件")
        else:
            ok = _ingest_files(f_users, f_sessions, f_feedback, show_reports=True)
            if ok:
                st.success("导入完成")

    if not auto_clicked and st.session_state.df_users is None and st.session_state.df_sessions is None:
        st.info("也可把文件放到项目 lists/ 或 D:\\FactoryAgentData\\uploads\\，重启后会自动加载。")

    if st.session_state.df_users is not None and st.session_state.df_sessions is not None:
        if "user_id" in st.session_state.df_users.columns and "user_id" in st.session_state.df_sessions.columns:
            u_users = set(st.session_state.df_users["user_id"].astype(str))
            s_users = set(st.session_state.df_sessions["user_id"].astype(str))
            diff = u_users ^ s_users
            st.markdown(f"**关联差异**：用户总表与会话表工厂相差 {len(diff)} 个")

    st.divider()
    st.markdown("### 历史批次")
    batches = storage.list_batches()
    if batches:
        st.dataframe(
            pd.DataFrame(batches)[
                ["id", "week_label", "file_name", "table_type", "row_count", "valid_count", "excluded_count", "created_at"]
            ]
        )
    else:
        st.info("暂无历史批次")


def render_overview():
    """首页概览：先结论，再指标。"""
    page_header("首页概览", "先看结论和动作，再下钻指标。数字全部本地计算。")
    if st.session_state.df_sessions is None and st.session_state.df_users is None:
        st.info("还没有数据。到「导入与质检」上传用户总表和会话表，或把 CSV 放到 lists/ 后重启。")
        return

    df = st.session_state.df_sessions
    dfu = st.session_state.df_users

    data = st.session_state.get("conclusion")
    if not data or data.get("来源") == "模型":
        data = insights.generate_local_conclusion(df, dfu)
        st.session_state.conclusion = data

    show_conclusion(data)

    actions = product.next_action_table(dfu)
    if not actions.empty:
        st.markdown("### 周报已给出的跟进动作")
        st.dataframe(actions)

    issues = product.issue_table(dfu, top_n=8)
    if not issues.empty:
        st.markdown("### 需跟进的问题工厂")
        show = issues.copy()
        if "问题摘要" in show.columns:
            show["问题摘要"] = show["问题摘要"].astype(str).str.slice(0, 80)
        if "company_name" in show.columns:
            show = show.drop(columns=["company_name"])
        st.dataframe(show)

    u_history = st.session_state.get("df_users_history", [])
    if len(u_history) >= 2:
        st.markdown("### 多周留存与环比")
        prev = u_history[-2]["df"]
        curr = u_history[-1]["df"]
        st.caption(f"对比周期：{u_history[-2]['week'] or '上周'} → {u_history[-1]['week'] or '本周'}")
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
            st.dataframe(wow)
    elif dfu is not None:
        st.caption("当前仅单周数据，再传一周用户总表可看工厂周留存与环比")

    if df is not None and not df.empty:
        metrics = product.collect_metrics(df, dfu)
        st.markdown("### 核心指标")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("有效提问数", metrics.get("有效提问数", 0))
        c2.metric("工厂数", metrics.get("工厂数", 0))
        c3.metric("会话数", metrics.get("会话数", 0))
        c4.metric("上传图纸次数", metrics.get("上传图纸次数", 0))
        week = ingestion.detect_week_label(df)
        st.caption(f"识别周次：{week or '无法识别'}")

        hf = product.intent_table(df)
        if not hf.empty:
            st.markdown("### 问法意图（本地归并）")
            st.dataframe(hf[["标准问题", "提问次数", "提问人数", "占比"]])

        ut = product.upload_type_table(df)
        if not ut.empty:
            st.markdown("### 上传图纸类型（已排除「无」）")
            st.dataframe(ut)

        exact = q.exact_questions(df, top_n=10)
        if not exact.empty:
            st.markdown("### 高频原话 Top 10")
            st.dataframe(exact)

    if dfu is not None and not dfu.empty:
        st.markdown("### 用户分群")
        group_cols = [c for c in ["scene", "level", "role", "member_type", "region", "process_type"] if c in dfu.columns]
        if group_cols:
            sel_group = st.selectbox("分群维度", group_cols)
            dist = dfu[sel_group].astype(str).value_counts()
            st.dataframe(pd.DataFrame({sel_group: dist.index, "数量": dist.values}))
        if "upload_count" in dfu.columns:
            uc = pd.to_numeric(dfu["upload_count"], errors="coerce").fillna(0)
            c1, c2, c3 = st.columns(3)
            c1.metric("周报上传工厂数", int((uc > 0).sum()))
            c2.metric("周报上传总数", int(uc.sum()))
            c3.metric("厂均上传", round(float(uc.mean()), 2))

    if st.session_state.df_feedback is not None and not st.session_state.df_feedback.empty:
        st.markdown("### 反馈表")
        st.dataframe(st.session_state.df_feedback.head(20))
