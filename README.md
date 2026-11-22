# novel-lint

**把长篇小说里「不能靠印象」的东西，变成能重跑的检查。**

写长篇最难的不是写，是别忘了：人物什么时候死的、伏笔埋在哪一章、稿本是不是混着改的。这些在设定文档里写着，但正文一多，人就开始凭印象——而**凭印象一定出错**。

`novel-lint` 只做机械项（对应自检表里那句「**工具只查机械项，文风只由人定**」）：它不评好坏，只告诉你哪里和设定冲突了。

零依赖，Python 3.10+。

## 三十秒跑起来

```bash
python -m novel_lint --config examples/sample/novel-lint.json
```

```text
3 个文件 · 2 个 error · 2 个 warning

── R001 · 1 处
  ✗ 第二章-承.md:5  禁用词「顿时」

── R005 · 1 处
  ✗ 第二章-承.md:3  周德威 已于 918 年死，本章为 921 年却仍出场

── R003 · 2 处
  ⚠ 第一章-起.md  正文 60 字，低于下限 80
```

## 真实输出（用一本 5 章的在写小说跑出来）

```text
files=9 issues=10
  R003 warning: 8
  R004 warning: 1
  R006 warning: 1

[warning] R003 第二章-无人死.md  正文 6240 字，高于上限 3200
[warning] R003 第一章-v4.md      正文 4642 字，高于上限 3200
[warning] R004 第一章-v4.md      「第一章」有 4 个稿本（v4, v3, v2, v0），默认用 v4
[warning] R006 第一章-v2.md      伏笔 #6「范九的纸卷」计划第 2 章揭，现已写到第 5 章仍未揭
[warning] R003 间章.md          正文 2445 字，低于下限 2500
```

四条值得说：

1. **第二章 6240 字，是上限的近两倍** —— 作者自己也没意识到。
2. **第一章有 4 个稿本** —— 混着引用会把旧稿当现行文本。
3. **伏笔 #6 逾期 3 章** —— 台账上写「第 2 章揭」，实际写到第 5 章还没揭。
4. 禁用词 **0 命中** —— 这条规则的价值一半在「没命中」：它证明作者确实在守。

## 规则

| 编号 | 检查 | 严重度 | 依据 |
|---|---|---|---|
| R001 | 禁用词表命中 | error | 文风红线 |
| R002 | 标记字（如「嗒」）每章超过上限 | warning | 出现多了会贬值 |
| R003 | 单章字数超出区间 | warning | 节奏 |
| R004 | 同一章存在多个稿本 | warning | 版本混用 |
| R005 | 已在某年死亡的人物，在其后年份仍出场 | error | 历史一致性 |
| R006 | 伏笔过了计划揭晓章节仍未揭 | warning | 台账 |

**为什么只有六级**：规则不是越多越好。每条规则都得能说清「为什么要有」，否则会变成一堆没人看的告警——那比没有更糟。

## 配置

```json
{
  "chapters": { "dir": "小说", "chars": [2500, 3200] },
  "bannedWords": ["顿时", "瞬间"],
  "marker": { "char": "嗒", "maxPerChapter": 3 },
  "timeline": [{ "year": 917, "era": "贞明三年", "age": 13 }],
  "deaths": [{ "name": "周德威", "year": 918 }],
  "foreshadow": [{ "id": 4, "planted": 1, "revealBy": 12, "status": "埋", "summary": "半枚铜鱼符" }]
}
```

**为什么用 JSON 而不是解析设定 Markdown**：把「设定」显式化，人改配置、工具读配置。解析自然语言表格是另一个项目的问题，混进来只会让两边都做不好。

## 用法

```bash
python -m novel_lint --config novel-lint.json            # 人看的报告
python -m novel_lint --config novel-lint.json --json     # 给 CI / 编辑器
python -m novel_lint --config novel-lint.json --strict   # warning 也算失败
python -m novel_lint --config novel-lint.json --dir 小说/新卷
```

退出码：`0` 干净，`1` 有 error（`--strict` 时含 warning），`2` 配置或目录有问题。

## 测试

```bash
python -m unittest discover -s tests -v
```

16 个用例，每条规则至少两个：一个「该报」、一个「不该报」。规则是纯函数，测试不需要真实小说。

## 已知限制

- **按年判断死亡边界**：同年内不再细分（严格说是「死在某年某月」，但正文通常只给年号）。
- **年号识别靠精确匹配**：正文里必须出现配置里的年号原文，否则该章跳过死亡检查（宁可不报，也不误报）。
- **不做语义检查**：人物性格走形、文风好坏，工具不管——那是人的事。

## 相关项目

三个项目同一个出发点——**把凭感觉的判断，变成能重跑两次的东西**：

- **[dsh-session-ledger](https://github.com/jjp-111/dsh-session-ledger)** —— Agent 会话的成本账本与策略回放：让「开新会话省不省钱」可测。
- **[dsh-plugin-session-guard](https://github.com/jjp-111/dsh-session-guard)** —— 给长会话执行成本策略：让「该不该换会话」可执行。

## 许可

MIT
