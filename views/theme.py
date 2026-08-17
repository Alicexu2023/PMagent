"""Ant Design tokens applied to Streamlit (Open Design bind: ant + dashboard)."""
from __future__ import annotations

import streamlit as st

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --pm-primary: #1677FF;
  --pm-primary-weak: #E6F4FF;
  --pm-success: #16A34A;
  --pm-warning: #D97706;
  --pm-danger: #DC2626;
  --pm-text: #111827;
  --pm-muted: #6B7280;
  --pm-surface: #FFFFFF;
  --pm-canvas: #F5F7FA;
  --pm-line: #E5E7EB;
  --pm-radius: 8px;
  --pm-shadow: 0 1px 2px rgba(17, 24, 39, 0.06);
}

html, body, [data-testid="stAppViewContainer"], .stApp {
  background: var(--pm-canvas) !important;
  color: var(--pm-text) !important;
  font-family: "Plus Jakarta Sans", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif !important;
}

[data-testid="stHeader"] {
  background: transparent !important;
}

[data-testid="stToolbar"] { display: none !important; }

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

.block-container {
  padding-top: 1.4rem !important;
  padding-bottom: 3rem !important;
  max-width: 1240px !important;
}

/* Sidebar — dashboard left rail 220–260px */
[data-testid="stSidebar"] {
  background: #001529 !important;
  min-width: 240px !important;
}
[data-testid="stSidebar"] * {
  color: #E5E7EB !important;
}
[data-testid="stSidebar"] .pm-brand {
  color: #FFFFFF !important;
}
[data-testid="stSidebar"] [data-testid="stCaption"] {
  color: #94A3B8 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
  padding: 8px 12px !important;
  border-radius: 6px !important;
  min-height: 36px;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
  background: rgba(255,255,255,0.06) !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
  background: var(--pm-primary) !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) span {
  color: #FFFFFF !important;
  font-weight: 600 !important;
}
[data-testid="stSidebar"] hr {
  border-color: rgba(255,255,255,0.12) !important;
}

/* KPI cards */
[data-testid="stMetric"] {
  background: var(--pm-surface);
  border: 1px solid var(--pm-line);
  border-radius: var(--pm-radius);
  padding: 16px 16px 12px 16px;
  box-shadow: var(--pm-shadow);
}
[data-testid="stMetric"] label { color: var(--pm-muted) !important; font-size: 12px !important; letter-spacing: 0.02em; }
[data-testid="stMetric"] [data-testid="stMetricValue"] { font-weight: 700 !important; color: var(--pm-text) !important; }

/* Dataframes */
[data-testid="stDataFrame"] {
  border: 1px solid var(--pm-line);
  border-radius: var(--pm-radius);
  overflow: hidden;
  background: var(--pm-surface);
}

/* Buttons */
.stButton > button {
  border-radius: 6px !important;
  min-height: 36px !important;
  font-weight: 600 !important;
  border: 1px solid var(--pm-line) !important;
}
.stButton > button[kind="primary"] {
  background: var(--pm-primary) !important;
  border-color: var(--pm-primary) !important;
  color: #fff !important;
}
.stButton > button:focus-visible {
  outline: 3px solid #91CAFF !important;
  outline-offset: 2px !important;
}

/* Headings */
h1, h2, h3 { color: var(--pm-text) !important; letter-spacing: -0.02em; }
.stMarkdown h3 { font-size: 1.05rem !important; margin-top: 1.4rem !important; }

/* Page header */
.pm-pagehead { margin: 0 0 1.25rem 0; }
.pm-pagehead h1 {
  font-size: 28px !important;
  font-weight: 700 !important;
  margin: 0 0 6px 0 !important;
  color: var(--pm-text) !important;
}
.pm-pagehead p {
  margin: 0 !important;
  color: var(--pm-muted) !important;
  font-size: 14px !important;
}

.pm-brand {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #fff;
  margin: 4px 0 2px 0;
}
.pm-brand-sub {
  font-size: 12px;
  color: #94A3B8;
  margin: 0 0 12px 0;
}

/* Conclusion card */
.pm-card {
  background: var(--pm-surface);
  border: 1px solid var(--pm-line);
  border-radius: 10px;
  padding: 18px 20px;
  box-shadow: var(--pm-shadow);
  margin: 0 0 16px 0;
}
.pm-card h2 {
  font-size: 13px !important;
  font-weight: 600 !important;
  color: var(--pm-muted) !important;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 0 0 10px 0 !important;
}
.pm-lead { font-size: 16px; line-height: 1.65; color: var(--pm-text); margin: 0 0 12px 0; }
.pm-meta { font-size: 13px; line-height: 1.6; color: var(--pm-muted); margin: 0 0 8px 0; }
.pm-action {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 0;
  border-top: 1px solid var(--pm-line);
  font-size: 14px;
  line-height: 1.5;
}
.pm-action:first-of-type { border-top: none; }
.pm-pri {
  flex: 0 0 auto;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--pm-primary-weak);
  color: var(--pm-primary);
}
.pm-pri-p0 { background: #FEE2E2; color: var(--pm-danger); }
.pm-pri-p1 { background: #FEF3C7; color: var(--pm-warning); }
.pm-pri-p2 { background: var(--pm-primary-weak); color: var(--pm-primary); }

.pm-chip {
  display: inline-block;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--pm-primary-weak);
  color: var(--pm-primary);
  font-weight: 600;
}
"""


def apply():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
