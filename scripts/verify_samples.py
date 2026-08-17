"""scripts/verify_samples.py — 样表验收：核对六个实测值。

开发.txt 要求：用户总表 370 行、会话表 3000 行、1468 个会话、371 家工厂、
2866 条非空问题；两表相差 1 家工厂，134 条问题为空。

样表位于桌面，路径可配置；缺失时退出码非 0 并说明原因。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 允许从项目根导入
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

# 期望的六个实测值（来自开发.txt）
EXPECT = {
    "用户总表行数": 370,
    "会话表行数": 3000,
    "会话数": 1468,
    "工厂数": 371,
    "非空问题数": 2866,
    "两表工厂差": 1,
}

# 样表可能的位置：桌面、项目 lists/、运行时数据目录
DESKTOP = Path.home() / "Desktop"
LISTS = ROOT / "lists"
DATA_DIR = Path(r"D:\FactoryAgentData")
SEARCH_DIRS = [LISTS, DESKTOP, DATA_DIR, DATA_DIR / "uploads"]

CANDIDATE_FILES = {
    "users": [DESKTOP / "用户总表.csv", DESKTOP / "用户表.csv"],
    "sessions": [DESKTOP / "会话表.csv", DESKTOP / "会话.csv"],
    "feedback": [DESKTOP / "客户反馈.xlsx", DESKTOP / "反馈表.xlsx"],
}


def find_file(key: str) -> Path | None:
    for p in CANDIDATE_FILES.get(key, []):
        if p.exists():
            return p
    for folder in SEARCH_DIRS:
        if not folder.exists():
            continue
        try:
            files = list(folder.glob("*.csv")) + list(folder.glob("*.xlsx"))
        except OSError:
            continue
        for p in files:
            name = p.name
            if key == "users" and ("用户" in name or "总表" in name or "user_report" in name.lower()):
                return p
            if key == "sessions" and ("会话" in name or "sessions_detail" in name.lower()):
                return p
            if key == "feedback" and "反馈" in name:
                return p
    return None


def main() -> int:
    errors = []

    # 用户总表
    uf = find_file("users")
    if uf is None:
        print("[缺失] 未找到用户总表 CSV（期望 370 行）")
        errors.append("用户总表缺失")
    else:
        try:
            du = pd.read_csv(uf, dtype=str, encoding="utf-8-sig")
            row = len(du)
            print(f"用户总表行数: {row} (期望 {EXPECT['用户总表行数']})")
            if row != EXPECT["用户总表行数"]:
                errors.append(f"用户总表行数 {row} != {EXPECT['用户总表行数']}")
        except UnicodeDecodeError:
            du = pd.read_csv(uf, dtype=str, encoding="gbk")
            row = len(du)
            print(f"用户总表行数(GBK): {row} (期望 {EXPECT['用户总表行数']})")
            if row != EXPECT["用户总表行数"]:
                errors.append(f"用户总表行数 {row} != {EXPECT['用户总表行数']}")

    # 会话表
    sf = find_file("sessions")
    if sf is None:
        print("[缺失] 未找到会话表 CSV（期望 3000 行）")
        errors.append("会话表缺失")
    else:
        try:
            ds = pd.read_csv(sf, dtype=str, encoding="utf-8-sig")
        except UnicodeDecodeError:
            ds = pd.read_csv(sf, dtype=str, encoding="gbk")
        rows = len(ds)
        print(f"会话表行数: {rows} (期望 {EXPECT['会话表行数']})")
        if rows != EXPECT["会话表行数"]:
            errors.append(f"会话表行数 {rows} != {EXPECT['会话表行数']}")

        # 会话数
        sess_col = None
        for c in ds.columns:
            if "会话" in str(c) or "session" in str(c).lower():
                sess_col = c
                break
        if sess_col:
            sess = ds[sess_col].nunique()
            print(f"会话数: {sess} (期望 {EXPECT['会话数']})")
            if sess != EXPECT["会话数"]:
                errors.append(f"会话数 {sess} != {EXPECT['会话数']}")

        # 工厂数
        fac_col = None
        for c in ds.columns:
            if "工厂" in str(c) or "公司" in str(c) or "factory" in str(c).lower():
                fac_col = c
                break
        if fac_col:
            fac = ds[fac_col].nunique()
            print(f"工厂数: {fac} (期望 {EXPECT['工厂数']})")
            if fac != EXPECT["工厂数"]:
                errors.append(f"工厂数 {fac} != {EXPECT['工厂数']}")

        # 非空问题数（NaN 与空字符串都算空）
        q_col = None
        for c in ds.columns:
            if "问题原文" in str(c) or "问题" in str(c) or "question" in str(c).lower():
                q_col = c
                break
        if q_col:
            nonempty = int((ds[q_col].notna() & (ds[q_col].astype(str).str.strip() != "")).sum())
            print(f"非空问题数: {nonempty} (期望 {EXPECT['非空问题数']})")
            if nonempty != EXPECT["非空问题数"]:
                errors.append(f"非空问题数 {nonempty} != {EXPECT['非空问题数']}")

    # 两表工厂差（用户总表 vs 会话表）
    if uf and sf and "du" in locals() and "ds" in locals():
        u_fac_col = next((c for c in du.columns if "工厂" in str(c) or "公司" in str(c)), None)
        s_fac_col = fac_col if "fac_col" in locals() else None
        if u_fac_col and s_fac_col:
            u_fac = set(du[u_fac_col].astype(str))
            s_fac = set(ds[s_fac_col].astype(str))
            diff = len(u_fac ^ s_fac)
            print(f"两表工厂差: {diff} (期望 {EXPECT['两表工厂差']})")
            if diff != EXPECT["两表工厂差"]:
                errors.append(f"两表工厂差 {diff} != {EXPECT['两表工厂差']}")

    if errors:
        print("\n[失败] 存在不一致：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\n[通过] 六个实测值全部一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
