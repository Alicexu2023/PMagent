"""core/config.py — 配置中心：模型配置、路径、阈值、字段映射、指标口径常量。

口径写死在代码与 README 中；改口径改代码。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env（若存在）
load_dotenv()

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
# 数据目录：开发.txt 指定 D:\FactoryAgentData；不存在则回退到项目 data/
_DATA_DIR_ENV = os.getenv("FACTORY_DATA_DIR", r"D:\FactoryAgentData")


def _resolve_data_dir() -> Path:
    d = Path(_DATA_DIR_ENV)
    try:
        d.mkdir(parents=True, exist_ok=True)
        # 试写，确认可写
        (d / ".write_test").touch(exist_ok=True)
        return d
    except Exception:
        # 回退到项目内 data/
        fallback = Path(__file__).resolve().parent.parent / "data"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


DATA_DIR = _resolve_data_dir()
DB_PATH = DATA_DIR / "factory_agent.sqlite"
UPLOAD_DIR = DATA_DIR / "uploads"

# ---------------------------------------------------------------------------
# 运行配置
# ---------------------------------------------------------------------------
HOST = os.getenv("FACTORY_HOST", "127.0.0.1")  # 只允许本机，禁止 0.0.0.0
PORT = int(os.getenv("FACTORY_PORT", "8000"))   # 开发.txt 默认 8000
APP_URL = f"http://{HOST}:{PORT}"

# ---------------------------------------------------------------------------
# DeepSeek / OpenAI 兼容配置
# ---------------------------------------------------------------------------
def _get_config(key: str, default: str = "") -> str:
    """优先从 Streamlit Cloud secrets 读取，回退到环境变量（本地 .env）。"""
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return os.getenv(key, default).strip()


DEEPSEEK_API_KEY = _get_config("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = _get_config("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = _get_config("DEEPSEEK_MODEL", "deepseek-chat")
AI_TIMEOUT_SECONDS = int(_get_config("AI_TIMEOUT_SECONDS", "60"))

# ---------------------------------------------------------------------------
# 指标口径阈值（写死，改口径改这里）
# ---------------------------------------------------------------------------
CONFIDENCE_THRESHOLD = 0.6          # 识别成功率：置信度 ≥ 0.6 视为识别成功
REPEAT_ASK_WINDOW_MIN = 10          # 重复提问：10 分钟内同用户再次问同一标准问题
RETENTION_SAMPLE_MIN = 30           # 留存组样本 < 30 人标注"样本不足"
MAX_TEXT_LENGTH = 500               # 超长文本处理阈值（字符）
MAX_ROWS = 100_000                  # 单次导入上限
RETENTION_PERIODS = [1, 7, 30]      # 留存周期：次日/7日/30日

# 有效回答状态集合（answer_status 命中即视为"有效回答"）
VALID_ANSWER_STATUS = {"成功", "有效", "success", "ok", "answered", "完成", "1"}

# 明确测试词（排除出"有效提问"）
TEST_WORDS = {"测试", "test", "test123", "hello", "你好"}

# ---------------------------------------------------------------------------
# 字段契约（必需性）
# ---------------------------------------------------------------------------
# 三张表的固定字段映射。value 为 None 表示"可选"，字符串为必需字段的规范化名。
# 导入时按这些字段做自动识别 + 固定映射。
REQUIRED_FIELDS = ["user_id", "event_time", "event_name"]

# 问答分析必需
QUESTION_FIELDS = ["question_id", "question_text"]
# 建议字段
SUGGESTED_FIELDS = ["session_id", "recognized_intent", "intent_confidence", "answer_status"]
# 可选字段
OPTIONAL_FIELDS = ["business_result", "page_name", "feature_name", "event_detail", "user_properties"]

ALL_FIELDS = (
    REQUIRED_FIELDS + QUESTION_FIELDS + SUGGESTED_FIELDS + OPTIONAL_FIELDS
)


def has_api_key() -> bool:
    """是否已配置 DeepSeek API Key。"""
    return bool(DEEPSEEK_API_KEY)


def mask_key(key: str | None = None) -> str:
    """脱敏显示密钥，只保留末尾 4 位。"""
    k = key if key is not None else DEEPSEEK_API_KEY
    if not k:
        return ""
    if len(k) <= 8:
        return "****"
    return f"****{k[-4:]}"
