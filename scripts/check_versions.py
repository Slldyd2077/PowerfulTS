#!/usr/bin/env python3
"""版本号一致性校验 —— 断言 SSOT 四处版本号完全相等。

commitizen 在 ``cz bump`` 时原子同步这四处，本脚本作为防线，防止有人手改
其中一处导致漂移。可手动运行，或接入 pre-commit / CI：

    python scripts/check_versions.py

退出码 0 = 全部一致，1 = 存在漂移。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 文件 → 提取版本号的正则；package.json 走 JSON 解析（pattern=None）
TARGETS: dict[str, str | None] = {
    "pyproject.toml": r'^version\s*=\s*"([^"]+)"',
    "backend/pyproject.toml": r'^version\s*=\s*"([^"]+)"',
    "backend/app/_version.py": r'^__version__\s*=\s*"([^"]+)"',
    "frontend/package.json": None,
}


def read_version(rel: str, pattern: str | None) -> str:
    path = ROOT / rel
    if not path.exists():
        raise SystemExit(f"[check-versions] 文件不存在: {rel}")
    text = path.read_text(encoding="utf-8")
    if pattern is None:
        return str(json.loads(text)["version"])
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise SystemExit(f"[check-versions] 未在 {rel} 找到版本号")
    return match.group(1)


def main() -> int:
    versions = {rel: read_version(rel, pat) for rel, pat in TARGETS.items()}
    for rel, ver in versions.items():
        print(f"  {rel:<32} {ver}")
    unique = set(versions.values())
    if len(unique) != 1:
        print("\n[check-versions] 版本号不一致，请用 cz bump 统一同步！")
        return 1
    print(f"\n[check-versions] 全部一致: {next(iter(unique))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
