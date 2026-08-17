"""views/common.py — 页面共用展示。"""
from __future__ import annotations

import html

import streamlit as st


def _e(text) -> str:
    return html.escape("" if text is None else str(text))


def page_header(title: str, subtitle: str = ""):
    extra = f"<p>{_e(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="pm-pagehead"><h1>{_e(title)}</h1>{extra}</div>',
        unsafe_allow_html=True,
    )


def show_conclusion(data: dict):
    if not data:
        return
    src = _e(data.get("来源") or "本地规则")
    lead = _e(data.get("结论", ""))
    evidence = _e(data.get("数据证据", ""))
    impact = _e(data.get("影响", ""))
    rj = data.get("原因判断") or {}
    supported = _e(rj.get("数据已支持", "")) if isinstance(rj, dict) else ""
    hypo = _e(rj.get("待验证假设", "")) if isinstance(rj, dict) else ""
    conf = data.get("置信度") or {}
    conf_line = ""
    if conf:
        conf_line = f'<p class="pm-meta">置信度 {_e(conf.get("等级", ""))} · {_e(conf.get("理由", ""))}</p>'

    actions_html = []
    for a in data.get("下一步动作") or []:
        pri = _e(a.get("优先级", "P1")).upper()
        cls = "pm-pri-p0" if pri == "P0" else "pm-pri-p1" if pri == "P1" else "pm-pri-p2"
        actions_html.append(
            f'<div class="pm-action"><span class="pm-pri {cls}">{pri}</span>'
            f'<div>{_e(a.get("动作", ""))}'
            f'<div class="pm-meta">目标指标：{_e(a.get("目标指标", ""))}</div></div></div>'
        )

    body = f"""
    <div class="pm-card">
      <h2>本周结论 <span class="pm-chip">{src}</span></h2>
      <p class="pm-lead">{lead}</p>
      {f'<p class="pm-meta"><strong>证据</strong> {evidence}</p>' if evidence else ''}
      {f'<p class="pm-meta"><strong>影响</strong> {impact}</p>' if impact else ''}
      {f'<p class="pm-meta"><strong>已支持</strong> {supported}</p>' if supported else ''}
      {f'<p class="pm-meta"><strong>待验证</strong> {hypo}</p>' if hypo else ''}
      {conf_line}
      {''.join(actions_html)}
    </div>
    """
    st.markdown(body, unsafe_allow_html=True)
    if data.get("证据警告"):
        st.warning(data["证据警告"])
