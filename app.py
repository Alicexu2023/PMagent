"""app.py — Streamlit 入口：侧边栏导航 + 视图挂载。

运行：streamlit run app.py --server.address 127.0.0.1 --server.port 8000
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from core import config, storage

st.set_page_config(
    page_title="工厂智能体分析平台",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _init():
    """初始化数据库与会话状态。"""
    storage.init_db()
    if "df_users" not in st.session_state:
        st.session_state.df_users = None
    if "df_sessions" not in st.session_state:
        st.session_state.df_sessions = None
    if "df_feedback" not in st.session_state:
        st.session_state.df_feedback = None
    if "df_users_history" not in st.session_state:
        st.session_state.df_users_history = []
    if "df_sessions_history" not in st.session_state:
        st.session_state.df_sessions_history = []
    if "reports" not in st.session_state:
        st.session_state.reports = {"users": None, "sessions": None, "feedback": None}
    if "current_page" not in st.session_state:
        st.session_state.current_page = "首页概览"
    if "autoload_done" not in st.session_state:
        st.session_state.autoload_done = False


def _classify_file(name: str) -> str | None:
    """按文件名关键词识别表类型。"""
    n = name.lower()
    if "用户总表" in name or "user_report" in n or "周使用用户" in name:
        return "users"
    if "会话" in name or "sessions_detail" in n or "供应商会话" in name:
        return "sessions"
    if "反馈" in name or "feedback" in n:
        return "feedback"
    return None


def _autoload():
    """启动时自动扫描本地已知数据文件并预加载，让用户打开即可看到结果。"""
    if st.session_state.autoload_done:
        return

    from analysis import ingestion

    # 候选目录：桌面 + 项目 data/ + 运行时数据目录
    candidates: list[Path] = []
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        candidates.append(desktop)
    proj_data = Path(__file__).resolve().parent / "data"
    if proj_data.exists():
        candidates.append(proj_data)
    if config.DATA_DIR.exists():
        candidates.append(config.DATA_DIR)

    files: dict[str, list[Path]] = {"users": [], "sessions": [], "feedback": []}
    seen: set[str] = set()
    for d in candidates:
        for p in d.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".csv", ".xlsx", ".xls"):
                continue
            t = _classify_file(p.name)
            if t is None:
                continue
            key = p.name
            if key in seen:
                continue
            seen.add(key)
            files[t].append(p)

    # 加载用户总表（多周）
    if files["users"]:
        history = []
        for p in files["users"]:
            try:
                df, rep = ingestion.ingest(p, "users", p.name)
                history.append({"df": df, "rep": rep, "week": rep.week_label, "file": p.name})
            except Exception:
                continue
        history.sort(key=lambda x: x["week"] or "")
        if history:
            st.session_state.df_users_history = history
            st.session_state.df_users = history[-1]["df"]

    # 加载会话表（多周）
    if files["sessions"]:
        shistory = []
        for p in files["sessions"]:
            try:
                df, rep = ingestion.ingest(p, "sessions", p.name)
                shistory.append({"df": df, "rep": rep, "week": rep.week_label, "file": p.name})
            except Exception:
                continue
        shistory.sort(key=lambda x: x["week"] or "")
        if shistory:
            st.session_state.df_sessions_history = shistory
            st.session_state.df_sessions = shistory[-1]["df"]

    # 反馈表（单张）
    if files["feedback"]:
        try:
            df, rep = ingestion.ingest(files["feedback"][0], "feedback", files["feedback"][0].name)
            st.session_state.df_feedback = df
            st.session_state.reports["feedback"] = rep
        except Exception:
            pass

    st.session_state.autoload_done = True


def main():
    _init()
    _autoload()

    # 侧边栏导航
    with st.sidebar:
        st.title("🏭 工厂智能体\n分析平台")
        st.caption("个人轻量版 · 本机运行")

        pages = [
            "导入与质检",
            "首页概览",
            "问答分析",
            "漏斗分析",
            "留存分析",
            "路径分析",
            "功能采用",
            "AI 结论与报告",
            "行动清单",
            "模型设置",
        ]
        choice = st.radio("导航", pages, key="nav",
                          index=pages.index(st.session_state.current_page) if st.session_state.current_page in pages else 0)
        st.session_state.current_page = choice

        st.divider()
        # 模型状态提示
        if config.has_api_key():
            st.success(f"模型已配置：{config.DEEPSEEK_MODEL}")
        else:
            st.warning("未配置 API Key，AI 功能不可用（本地分析不受影响）")

    # 视图挂载
    from views import import_view, questions_view, analytics_view, paths_view, adoption_view, actions_view, insights_view, settings_view

    if choice == "导入与质检":
        import_view.render()
    elif choice == "首页概览":
        import_view.render_overview()
    elif choice == "问答分析":
        questions_view.render()
    elif choice == "漏斗分析":
        analytics_view.render_funnel()
    elif choice == "留存分析":
        analytics_view.render_retention()
    elif choice == "路径分析":
        paths_view.render()
    elif choice == "功能采用":
        adoption_view.render()
    elif choice == "AI 结论与报告":
        insights_view.render()
    elif choice == "行动清单":
        actions_view.render()
    elif choice == "模型设置":
        settings_view.render()


if __name__ == "__main__":
    main()
