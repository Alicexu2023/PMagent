"""scripts/health_check.py — 本地健康检查 + 监听地址安全校验。

1. 校验启动配置 HOST 必须是 127.0.0.1（故意改成 0.0.0.0 时测试变红）。
2. 检查 127.0.0.1:8000 是否可达（Streamlit 服务）。
"""
from __future__ import annotations

import socket
import sys
import urllib.request

HOST = "127.0.0.1"
PORT = 8000


def check_host_config() -> bool:
    """校验监听地址配置必须为 127.0.0.1，禁止 0.0.0.0。"""
    try:
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
        from core import config
        if config.HOST != "127.0.0.1":
            print(f"[失败] 监听地址配置为 {config.HOST}，必须是 127.0.0.1（禁止 0.0.0.0）")
            return False
        return True
    except Exception as e:
        print(f"[失败] 无法读取监听地址配置：{e}")
        return False


def check_port() -> bool:
    """检查 127.0.0.1:8000 是否监听。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        return s.connect_ex((HOST, PORT)) == 0


def check_http() -> bool:
    """HTTP 请求确认是 Streamlit。"""
    try:
        resp = urllib.request.urlopen(f"http://{HOST}:{PORT}", timeout=3)
        return resp.status == 200
    except Exception:
        return False


def main() -> int:
    failures = []
    if not check_host_config():
        failures.append("监听地址配置")
    if not check_port():
        failures.append(f"127.0.0.1:{PORT} 未监听")
        print(f"[失败] 127.0.0.1:{PORT} 未监听。请先运行 start.bat")
    elif not check_http():
        failures.append("HTTP 响应异常")
        print(f"[失败] 127.0.0.1:{PORT} HTTP 响应异常")

    if failures:
        return 1
    print(f"[通过] 监听地址 127.0.0.1 安全，127.0.0.1:{PORT} 健康检查成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
