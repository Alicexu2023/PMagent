"""Launch scripts must stay ASCII so cmd.exe (GBK) never mojibakes them."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _assert_ascii(path: Path):
    raw = path.read_bytes()
    raw.decode("ascii")
    assert not raw.startswith(b"\xff\xfe"), f"{path.name} is UTF-16"


def test_start_bat_is_ascii():
    _assert_ascii(ROOT / "start.bat")


def test_start_ps1_is_ascii():
    _assert_ascii(ROOT / "start.ps1")


def test_start_bat_sets_utf8():
    text = (ROOT / "start.bat").read_text(encoding="ascii")
    assert "PYTHONUTF8=1" in text
    assert "start.ps1" in text
