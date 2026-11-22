#!/usr/bin/env python3
"""命令行入口：python -m novel_lint --config novel-lint.json"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import Config, lint


def render(issues, paths) -> str:
    if not issues:
        return f"✓ {len(paths)} 个文件，没有发现问题"

    lines = []
    errors = [i for i in issues if i.severity == "error"]
    warns = [i for i in issues if i.severity == "warning"]
    lines.append(f"{len(paths)} 个文件 · {len(errors)} 个 error · {len(warns)} 个 warning")
    lines.append("")

    by_rule: dict[str, list] = {}
    for issue in issues:
        by_rule.setdefault(issue.rule, []).append(issue)

    for rule, group in by_rule.items():
        lines.append(f"── {rule} · {len(group)} 处")
        for i in group:
            where = Path(i.file).name + (f":{i.line}" if i.line else "")
            mark = "✗" if i.severity == "error" else "⚠"
            lines.append(f"  {mark} {where}  {i.message}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台默认 GBK，输出 ✗/⚠ 会直接抛 UnicodeEncodeError。
    # 强制 UTF-8 并允许替换，保证在管道/文件里也是正确编码。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(prog="novel-lint", description="检查小说正文与设定是否一致")
    ap.add_argument("--config", default="novel-lint.json", help="配置文件（默认 novel-lint.json）")
    ap.add_argument("--dir", default="", help="覆盖配置里的正文目录")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--strict", action="store_true", help="warning 也算失败")
    args = ap.parse_args(argv)

    try:
        cfg = Config.load(args.config)
    except FileNotFoundError:
        print(f"找不到配置：{args.config}", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, KeyError, IndexError, ValueError) as err:
        print(f"配置读不了：{err}", file=sys.stderr)
        return 2

    root = Path(args.dir or cfg.chapters_dir)
    if not root.is_absolute() and not root.exists():
        # 配置里的相对目录，先按当前目录找，找不到就按配置文件所在目录找——
        # 这样 `--config examples/sample/novel-lint.json` 不用先 cd 过去。
        alt = Path(args.config).parent / cfg.chapters_dir
        if alt.exists():
            root = alt
    if not root.exists():
        print(f"正文目录不存在：{root}", file=sys.stderr)
        return 2

    paths = sorted(p for p in root.rglob("*.md") if p.is_file())
    if not paths:
        print(f"{root} 下没有 .md 文件", file=sys.stderr)
        return 2

    issues = lint(paths, cfg)

    if args.json:
        print(json.dumps([i.as_dict() for i in issues], ensure_ascii=False, indent=2))
    else:
        print(render(issues, paths))

    failed = any(i.severity == "error" for i in issues) or (args.strict and issues)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
