"""scripts/scan_secrets.py — 密钥泄漏扫描。

扫描代码/日志/报告，检测是否出现真实 API Key 或 .env 内容。
零命中 = 退出码 0。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# DeepSeek/OpenAI key 模式：sk- 开头 + 长串
KEY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-_]{20,}"),
]

# 排除的文件/目录
EXCLUDE_DIRS = {".venv", "venv", "__pycache__", ".git", ".pytest_cache", "node_modules"}
EXCLUDE_FILES = {".env"}  # .env 本身是密钥存放地，不扫描其内容，但代码里不应引用


def scan() -> int:
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(d in p.parts for d in EXCLUDE_DIRS):
            continue
        if p.name in EXCLUDE_FILES or p.name.startswith("."):
            continue
        if p.suffix.lower() not in {".py", ".md", ".bat", ".ps1", ".txt", ".log", ".json"}:
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in KEY_PATTERNS:
            for m in pat.finditer(content):
                hits.append((str(p.relative_to(ROOT)), m.group(0)[:20] + "..."))

    if hits:
        print("[失败] 检测到疑似密钥泄漏：")
        for f, k in hits:
            print(f"  - {f}: {k}")
        return 1
    print("[通过] 密钥泄漏扫描零命中")
    return 0


if __name__ == "__main__":
    sys.exit(scan())
