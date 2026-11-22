"""
novel-lint 核心：把「设定文档」变成可执行的检查规则。

设计原则（对应自检表里那句「工具只查机械项，文风只由人定」）：
  - 每条规则都是纯函数：输入（正文文本 + 配置）→ 输出问题列表，不读环境、不联网；
  - 每条规则都有自己的编号（R001…），报错能直接对到代码，测试能直接对它断言；
  - 严重度只有 error / warning 两级：error = 设定崩了，warning = 需要人看一眼。

配置走 JSON（不解析 Markdown 表格）：把「设定」显式化，人改配置、工具读配置。
解析自然语言表格是另一种能力的项目，不是这个工具的卖点。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


@dataclass
class Issue:
    rule: str
    severity: str  # error | warning
    file: str
    line: int
    message: str

    def as_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "file": self.file, "line": self.line, "message": self.message}


@dataclass
class Config:
    chapters_dir: str = "."
    chars_min: int = 2500
    chars_max: int = 3200
    banned_words: list[str] = field(default_factory=list)
    marker_char: str = "嗒"
    marker_max: int = 3
    timeline: list[dict] = field(default_factory=list)  # {year, era, age}
    deaths: list[dict] = field(default_factory=list)  # {name, year, aliases?}
    foreshadow: list[dict] = field(default_factory=list)  # {id, planted, revealBy, status}

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        chapters = raw.get("chapters", {})
        chars = chapters.get("chars", [2500, 3200])
        return cls(
            chapters_dir=chapters.get("dir", "."),
            chars_min=int(chars[0]),
            chars_max=int(chars[1]),
            banned_words=list(raw.get("bannedWords", [])),
            marker_char=raw.get("marker", {}).get("char", "嗒"),
            marker_max=int(raw.get("marker", {}).get("maxPerChapter", 3)),
            timeline=list(raw.get("timeline", [])),
            deaths=list(raw.get("deaths", [])),
            foreshadow=list(raw.get("foreshadow", [])),
        )


# ── 章节解析 ────────────────────────────────────────────────────
CH_NUM_RE = re.compile(r"第([一二三四五六七八九十]+)章")
VERSION_RE = re.compile(r"-v(\d+)$", re.IGNORECASE)


def chapter_number(path: Path) -> int | None:
    """从文件名取章号；「间章」不算正章，返回 None。"""
    m = CH_NUM_RE.search(path.stem)
    if not m:
        return None
    raw = m.group(1)
    if raw in CN_NUM:
        return CN_NUM[raw]
    if raw.startswith("十"):
        tail = raw[1:]
        return 10 + (CN_NUM.get(tail, 0) if tail else 0)
    return None


def version_of(path: Path) -> int:
    m = VERSION_RE.search(path.stem)
    return int(m.group(1)) if m else 0


def chapter_key(path: Path) -> str:
    return VERSION_RE.sub("", path.stem)


def body_chars(path: Path) -> int:
    """正文字数：去掉空白与标题符号，只数可见字符。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.MULTILINE)
    return len(re.sub(r"\s+", "", text))


def detect_year(text: str, timeline: list[dict]) -> tuple[int | None, int]:
    """在正文里找最先出现的年号，返回 (year, 行号)。按年号长度倒序匹配，避免「贞明三年」被「贞明」截断。"""
    eras = sorted((t for t in timeline if t.get("era")), key=lambda t: -len(str(t["era"])))
    for lineno, line in enumerate(text.splitlines(), 1):
        for item in eras:
            if str(item["era"]) in line:
                return int(item["year"]), lineno
    return None, 0


# ── 规则 ────────────────────────────────────────────────────────
def rule_banned_words(paths: list[Path], cfg: Config) -> list[Issue]:
    """R001 禁用词：出现即改。"""
    issues = []
    words = [w for w in cfg.banned_words if w]
    if not words:
        return issues
    pattern = re.compile("|".join(map(re.escape, words)))
    for path in paths:
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in pattern.finditer(line):
                issues.append(Issue("R001", "error", str(path), lineno, f"禁用词「{m.group(0)}」"))
    return issues


def rule_marker_quota(paths: list[Path], cfg: Config) -> list[Issue]:
    """R002 标记字配额：每章 1–3 次，超过就贬值。"""
    issues = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        times = text.count(cfg.marker_char)
        if times > cfg.marker_max:
            issues.append(
                Issue("R002", "warning", str(path), 0, f"「{cfg.marker_char}」出现 {times} 次（上限 {cfg.marker_max}），会贬值")
            )
    return issues


def rule_chapter_length(paths: list[Path], cfg: Config) -> list[Issue]:
    """R003 单章字数区间。"""
    issues = []
    for path in paths:
        n = body_chars(path)
        if n < cfg.chars_min:
            issues.append(Issue("R003", "warning", str(path), 0, f"正文 {n} 字，低于下限 {cfg.chars_min}"))
        elif n > cfg.chars_max:
            issues.append(Issue("R003", "warning", str(path), 0, f"正文 {n} 字，高于上限 {cfg.chars_max}"))
    return issues


def rule_version_mix(paths: list[Path], cfg: Config) -> list[Issue]:
    """R004 同一章存在多稿：混着引用会把旧稿当现行文本。"""
    groups: dict[str, list[Path]] = {}
    for path in paths:
        groups.setdefault(chapter_key(path), []).append(path)
    issues = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        versions = sorted((version_of(p) for p in group), reverse=True)
        canonical = max(group, key=version_of)
        issues.append(
            Issue(
                "R004",
                "warning",
                str(canonical),
                0,
                f"「{key}」有 {len(group)} 个稿本（v{', v'.join(map(str, versions))}），默认用 v{version_of(canonical)}",
            )
        )
    return issues


def rule_dead_after_death(paths: list[Path], cfg: Config) -> list[Issue]:
    """R005 死者不能复活：人物在死亡年份之后仍出场，即设定崩。

    依赖：配置里声明人物死亡年份，正文里能认出年号（timeline 提供 年号→年份）。
    """
    issues = []
    if not cfg.deaths or not cfg.timeline:
        return issues
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        year, _ = detect_year(text, cfg.timeline)
        if year is None:
            continue
        cited = None
        for death in cfg.deaths:
            names = [death.get("name")] + list(death.get("aliases", []))
            for name in filter(None, names):
                if str(name) not in text:
                    continue
                if year > int(death["year"]):
                    lineno = next((i for i, l in enumerate(text.splitlines(), 1) if str(name) in l), 0)
                    issues.append(
                        Issue(
                            "R005",
                            "error",
                            str(path),
                            lineno,
                            f"{name} 已于 {death['year']} 年死，本章为 {year} 年却仍出场",
                        )
                    )
                    cited = name
                break
            if cited:
                break
    return issues


def rule_foreshadow_overdue(paths: list[Path], cfg: Config) -> list[Issue]:
    """R006 伏笔逾期：过了计划揭晓的章还没揭。"""
    issues = []
    if not cfg.foreshadow:
        return issues
    current = max((chapter_number(p) or 0 for p in paths), default=0)
    for item in cfg.foreshadow:
        status = str(item.get("status", "埋"))
        reveal_by = int(item.get("revealBy", 0) or 0)
        if not reveal_by or status != "埋":
            continue
        if current >= reveal_by:
            issues.append(
                Issue(
                    "R006",
                    "warning",
                    str(paths[0]) if paths else "",
                    0,
                    f"伏笔 #{item.get('id')}「{item.get('summary', '')}」计划第 {reveal_by} 章揭，现已写到第 {current} 章仍未揭",
                )
            )
    return issues


RULES = (
    rule_banned_words,
    rule_marker_quota,
    rule_chapter_length,
    rule_version_mix,
    rule_dead_after_death,
    rule_foreshadow_overdue,
)


def lint(paths: list[Path], cfg: Config) -> list[Issue]:
    issues: list[Issue] = []
    for rule in RULES:
        issues.extend(rule(paths, cfg))
    issues.sort(key=lambda i: (i.severity != "error", i.file, i.line))
    return issues
