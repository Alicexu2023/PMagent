"""views/settings_view.py — 模型配置 / 测试连接。"""
from __future__ import annotations

import streamlit as st

from analysis import ai_client
from core import config


def render():
    st.header("模型设置")
    st.caption("默认 DeepSeek，OpenAI 兼容接口，可换 GPT / Qwen")

    st.markdown(f"**当前模型**：{config.DEEPSEEK_MODEL}")
    st.markdown(f"**Base URL**：{config.DEEPSEEK_BASE_URL}")

    if config.has_api_key():
        st.success(f"API Key 已配置（{config.mask_key()}）")
    else:
        st.info("未配置 API Key。本地结论、问法归并、漏斗和图纸采用仍可用。要模型润色时再填 Key。")

    st.markdown("""
### 配置方式

1. 复制项目根目录的 `.env.example` 为 `.env`
2. 填入 `DEEPSEEK_API_KEY=sk-xxx`
3. 重启平台

密钥只从环境变量读取，不会写入代码、日志或报告。
    """)

    # 测试连接
    st.divider()
    st.markdown("### 测试连接")
    if not config.has_api_key():
        st.info("未配置 Key，无法测试连接")
        return
    if st.button("测试连接"):
        with st.spinner("测试中..."):
            content, err = ai_client.chat(
                [{"role": "user", "content": "回复：连接成功"}]
            )
            if err:
                st.error(err)
            else:
                st.success(f"连接成功，模型返回：{content}")

    # 展示脱敏功能
    st.divider()
    st.markdown("### 脱敏功能验证")
    test_text = st.text_input("输入含敏感信息的文本", placeholder="请联系 13800138000 或 a@b.com")
    if test_text and st.button("脱敏预览"):
        st.code(ai_client.desensitize(test_text))
