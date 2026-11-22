"""
规则测试：每条规则一个用例，全部是纯函数调用，不碰网络、不需要真实小说。

跑法：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import itertools
import json
import shutil
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from novel_lint.core import (  # noqa: E402
    Config,
    chapter_number,
    chapter_key,
    detect_year,
    rule_banned_words,
    rule_chapter_length,
    rule_dead_after_death,
    rule_foreshadow_overdue,
    rule_marker_quota,
    rule_version_mix,
)


FIXTURES = Path(__file__).resolve().parent / ".fixtures"
_counter = itertools.count()


@contextmanager
def tmpdir():
    """
    用固定目录而不是 tempfile.mkdtemp：
    Windows 沙箱会给 mkdtemp 建出的目录一套不允许写入的 ACL，导致用例全红；
    预先存在的目录则正常。所以这里自己建、自己清。
    """
    FIXTURES.mkdir(parents=True, exist_ok=True)
    d = FIXTURES / f"c{next(_counter)}"
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir()
    try:
        yield d
    finally:
        pass  # 保留现场，排查失败用例时有用；.fixtures 已 gitignore


def write(tmp: Path, name: str, text: str) -> Path:
    path = tmp / name
    path.write_text(text, encoding="utf-8")
    return path


def cfg(**kw) -> Config:
    base = dict(
        banned_words=["顿时", "瞬间"],
        marker_char="嗒",
        marker_max=3,
        chars_min=10,
        chars_max=1000,
        timeline=[
            {"year": 917, "era": "贞明三年", "age": 13},
            {"year": 918, "era": "贞明四年", "age": 14},
            {"year": 921, "era": "龙德元年", "age": 17},
        ],
        deaths=[{"name": "周德威", "year": 918}, {"name": "张承业", "year": 921, "aliases": ["承业"]}],
        foreshadow=[{"id": 4, "planted": 1, "revealBy": 12, "status": "埋", "summary": "铜鱼符"}],
    )
    base.update(kw)
    return Config(**base)


class ChapterParsing(unittest.TestCase):
    def test_chapter_number_from_chinese(self):
        self.assertEqual(chapter_number(Path("第一章-贞明三年-v4.md")), 1)
        self.assertEqual(chapter_number(Path("第三章-数.md")), 3)
        self.assertEqual(chapter_number(Path("第五章-两拨人.md")), 5)
        self.assertIsNone(chapter_number(Path("间章-韩贲.md")))

    def test_version_stripped_for_key(self):
        self.assertEqual(chapter_key(Path("第一章-贞明三年-v4.md")), "第一章-贞明三年")
        self.assertNotEqual(chapter_key(Path("第一章-贞明三年-v3.md")), "第一章-贞明三年-v4")

    def test_detect_year_picks_longest_era(self):
        year, _ = detect_year("贞明三年冬，风从北边来。", cfg().timeline)
        self.assertEqual(year, 917)


class BannedWords(unittest.TestCase):
    def test_reports_each_occurrence(self):
        with tmpdir() as d:
            p = write(Path(d), "第一章.md", "他顿时停住。\n她瞬间回头，顿时明白。")
            issues = rule_banned_words([p], cfg())
            self.assertEqual(len(issues), 3)
            self.assertTrue(all(i.rule == "R001" and i.severity == "error" for i in issues))

    def test_clean_text_passes(self):
        with tmpdir() as d:
            p = write(Path(d), "第一章.md", "他停住，手还按在门上。")
            self.assertEqual(rule_banned_words([p], cfg()), [])


class MarkerQuota(unittest.TestCase):
    def test_over_quota_warns(self):
        with tmpdir() as d:
            p = write(Path(d), "第二章.md", "\n".join(["嗒"] * 4))
            issues = rule_marker_quota([p], cfg())
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].rule, "R002")

    def test_at_quota_passes(self):
        with tmpdir() as d:
            p = write(Path(d), "第二章.md", "\n".join(["嗒"] * 3))
            self.assertEqual(rule_marker_quota([p], cfg()), [])


class ChapterLength(unittest.TestCase):
    def test_short_and_long_both_reported(self):
        with tmpdir() as d:
            short = write(Path(d), "第一章.md", "短")
            long = write(Path(d), "第二章.md", "字" * 2000)
            issues = rule_chapter_length([short, long], cfg(chars_min=10, chars_max=1000))
            self.assertEqual(len(issues), 2)
            self.assertTrue(all(i.rule == "R003" for i in issues))


class VersionMix(unittest.TestCase):
    def test_multiple_versions_of_one_chapter_warns_once(self):
        with tmpdir() as d:
            a = write(Path(d), "第一章-v3.md", "旧稿")
            b = write(Path(d), "第一章-v4.md", "新稿")
            c = write(Path(d), "第二章.md", "另一章")
            issues = rule_version_mix([a, b, c], cfg())
            self.assertEqual(len(issues), 1)
            self.assertIn("v4", issues[0].message)
            self.assertIn("第一章-v4", issues[0].file)


class DeadAfterDeath(unittest.TestCase):
    def test_dead_character_cannot_appear_later(self):
        with tmpdir() as d:
            # 921 年，周德威 918 已死
            p = write(Path(d), "第七章.md", "龙德元年，周德威在帐里说话。")
            issues = rule_dead_after_death([p], cfg())
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].rule, "R005")
            self.assertIn("918", issues[0].message)

    def test_same_year_or_earlier_is_fine(self):
        with tmpdir() as d:
            p = write(Path(d), "第二章.md", "贞明四年，周德威站在城下。")
            self.assertEqual(rule_dead_after_death([p], cfg()), [])

    def test_alias_matches(self):
        with tmpdir() as d:
            # 用别名「承业」，且把死亡年份设为更早，确保是「别名命中」在起作用
            p = write(Path(d), "第八章.md", "龙德元年，承业没说话。")
            issues = rule_dead_after_death([p], cfg(deaths=[{"name": "张承业", "year": 918, "aliases": ["承业"]}]))
            self.assertEqual(len(issues), 1)
            self.assertIn("承业", issues[0].message)


class Foreshadow(unittest.TestCase):
    def test_overdue_when_past_reveal_chapter(self):
        with tmpdir() as d:
            p = write(Path(d), "第十二章.md", "正文")
            issues = rule_foreshadow_overdue([p], cfg())
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0].rule, "R006")

    def test_not_overdue_before_reveal_chapter(self):
        with tmpdir() as d:
            p = write(Path(d), "第五章.md", "正文")
            self.assertEqual(rule_foreshadow_overdue([p], cfg()), [])

    def test_revealed_item_not_reported(self):
        with tmpdir() as d:
            p = write(Path(d), "第十二章.md", "正文")
            revealed = cfg(foreshadow=[{"id": 4, "revealBy": 12, "status": "已揭", "summary": "x"}])
            self.assertEqual(rule_foreshadow_overdue([p], revealed), [])


class ConfigLoading(unittest.TestCase):
    def test_loads_and_normalises(self):
        with tmpdir() as d:
            path = Path(d) / "novel-lint.json"
            path.write_text(
                json.dumps(
                    {
                        "chapters": {"dir": "小说", "chars": [2500, 3200]},
                        "bannedWords": ["顿时"],
                        "marker": {"char": "嗒", "maxPerChapter": 2},
                        "timeline": [{"year": 917, "era": "贞明三年", "age": 13}],
                    }
                ),
                encoding="utf-8",
            )
            config = Config.load(path)
            self.assertEqual(config.chapters_dir, "小说")
            self.assertEqual((config.chars_min, config.chars_max), (2500, 3200))
            self.assertEqual(config.marker_max, 2)


if __name__ == "__main__":
    unittest.main()
