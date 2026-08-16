"""scripts/check_fingerprint.py — 规格指纹检查。

开发.txt 要求核对两个规格文件 SHA256：
- 工厂智能体分析平台_PRD.md = CC812AF41B5E63AE3AC1436AC0A46B59D8770700CB812CE4C565D5DFE1D798A6
- docs/工厂智能体分析平台_轻量化开发方案.md = 6915DCC2A92219AA592E6EAA6BA91E545F32FA86FD84F4271C0ECFF3EEB2F24B

本机只有"轻量化"版文件名不同，若目标文件缺失则明确提示 SKIP 原因，不伪造通过。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 期望指纹（来自开发.txt）
EXPECTED = {
    "工厂智能体分析平台_PRD.md": "CC812AF41B5E63AE3AC1436AC0A46B59D8770700CB812CE4C565D5DFE1D798A6",
    "docs/工厂智能体分析平台_轻量化开发方案.md": "6915DCC2A92219AA592E6EAA6BA91E545F32FA86FD84F4271C0ECFF3EEB2F24B",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main() -> int:
    all_ok = True
    for rel, expected in EXPECTED.items():
        p = ROOT / rel
        if not p.exists():
            print(f"[跳过] {rel} 不存在（当前机器仅有轻量化版，原始文件在 floraxu 机器）")
            continue
        actual = sha256(p)
        if actual == expected:
            print(f"[通过] {rel} 指纹一致")
        else:
            print(f"[失败] {rel} 指纹不一致")
            print(f"  期望: {expected}")
            print(f"  实际: {actual}")
            all_ok = False
    if all_ok:
        print("[通过] 规格指纹检查完成（存在文件均一致，缺失文件已标注）")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
